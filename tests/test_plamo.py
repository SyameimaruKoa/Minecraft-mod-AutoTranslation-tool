import unittest
from unittest.mock import Mock, patch

from mod_translator import build_plamo_prompt, resolve_plamo_model, translate_with_plamo


def response_with(text, finish_reason="stop"):
    response = Mock()
    response.json.return_value = {"choices": [{"text": text, "finish_reason": finish_reason}]}
    return response


class PlamoTranslationTests(unittest.TestCase):
    def test_prompt_uses_pfml3_and_plain_japanese(self):
        prompt = build_plamo_prompt("Open settings")
        self.assertTrue(prompt.startswith("<|plamo:tag|>dataset<|plamo:msg|>translation"))
        self.assertIn("<|plamo:tag|>input<|plamo:key|>lang<|plamo:val|>en<|plamo:msg|>Open settings", prompt)
        self.assertTrue(prompt.endswith("<|plamo:key|>form<|plamo:val|>plain<|plamo:msg|>"))

    def test_polite_form(self):
        self.assertIn("<|plamo:key|>form<|plamo:val|>polite", build_plamo_prompt("Hello", "polite"))

    @patch("mod_translator.requests.get")
    def test_lm_studio_model_id_autodetection(self, get):
        get.return_value.json.return_value = {
            "data": [{"id": "other-model"}, {"id": "pfnet/plamo-3-translate-2b-GGUF"}]
        }
        model = resolve_plamo_model("http://127.0.0.1:1234/v1/completions")
        self.assertEqual(model, "pfnet/plamo-3-translate-2b-GGUF")
        get.assert_called_once_with("http://127.0.0.1:1234/v1/models", timeout=10)

    @patch("mod_translator.requests.get")
    def test_multiple_plamo_models_need_explicit_choice(self, get):
        get.return_value.json.return_value = {
            "data": [{"id": "plamo-3-translate-2b"}, {"id": "plamo-3-translate-8b"}]
        }
        with self.assertRaisesRegex(RuntimeError, "--model"):
            resolve_plamo_model("http://127.0.0.1:1234/v1/completions")

    @patch("mod_translator.requests.get")
    def test_no_plamo_model_does_not_select_other_model(self, get):
        get.return_value.json.return_value = {"data": [{"id": "qwen3-8b"}]}
        with self.assertRaisesRegex(RuntimeError, "PLaMo 3 TranslateがLM Studio"):
            resolve_plamo_model("http://127.0.0.1:1234/v1/completions")

    @patch("mod_translator.requests.post")
    def test_calls_completions_api_once_per_unique_text(self, post):
        post.return_value = response_with("石")
        result = translate_with_plamo({"a": "Stone", "b": "Stone"}, model_name="test-model", api_url="http://localhost:8080/v1/completions")
        self.assertEqual(result, {"a": "石", "b": "石"})
        self.assertEqual(post.call_count, 1)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://localhost:8080/v1/completions")
        self.assertEqual(kwargs["json"]["model"], "test-model")
        self.assertEqual(kwargs["json"]["stop"], ["<|plamo:tag|>", "<|plamo:bos|>"])
        self.assertEqual(kwargs["json"]["temperature"], 0)

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_retries_when_placeholders_change(self, post, sleep):
        post.side_effect = [response_with("石 %d"), response_with("石 %s")]
        result = translate_with_plamo({"a": "Stone %s"}, model_name="plamo-3-translate-2b")
        self.assertEqual(result, {"a": "石 %s"})
        self.assertEqual(post.call_count, 2)

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_preserves_original_on_invalid_responses(self, post, sleep):
        post.return_value = response_with("石 %d")
        self.assertEqual(translate_with_plamo({"a": "Stone %s"}, model_name="plamo-3-translate-2b"), {})
        self.assertEqual(post.call_count, 3)

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_retries_truncated_responses(self, post, sleep):
        post.side_effect = [response_with("不完全", "length"), response_with("完全")]
        self.assertEqual(translate_with_plamo({"a": "Complete"}, model_name="plamo-3-translate-2b"), {"a": "完全"})
        self.assertEqual(post.call_count, 2)

    @patch("mod_translator.requests.post")
    def test_fails_fast_when_server_is_unavailable(self, post):
        from requests.exceptions import ConnectionError
        post.side_effect = ConnectionError("offline")
        with self.assertRaisesRegex(RuntimeError, "PLaMoサーバーに接続できません"):
            translate_with_plamo({"a": "Stone"}, model_name="plamo-3-translate-2b")


if __name__ == "__main__":
    unittest.main()
