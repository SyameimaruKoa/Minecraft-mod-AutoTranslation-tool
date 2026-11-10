import unittest
from unittest.mock import Mock, patch

from mod_translator import build_plamo_prompt, translate_with_plamo


def response_with(text):
    response = Mock()
    response.json.return_value = {"choices": [{"text": text}]}
    return response


class PlamoTranslationTests(unittest.TestCase):
    def test_prompt_uses_pfml3_and_plain_japanese(self):
        prompt = build_plamo_prompt("Open settings")
        self.assertTrue(prompt.startswith("<|plamo:tag|>dataset<|plamo:msg|>translation"))
        self.assertIn("<|plamo:tag|>input<|plamo:key|>lang<|plamo:val|>en<|plamo:msg|>Open settings", prompt)
        self.assertTrue(prompt.endswith("<|plamo:key|>form<|plamo:val|>plain<|plamo:msg|>"))

    def test_polite_form(self):
        self.assertIn("<|plamo:key|>form<|plamo:val|>polite", build_plamo_prompt("Hello", "polite"))

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
        result = translate_with_plamo({"a": "Stone %s"})
        self.assertEqual(result, {"a": "石 %s"})
        self.assertEqual(post.call_count, 2)

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_preserves_original_on_invalid_responses(self, post, sleep):
        post.return_value = response_with("石 %d")
        self.assertEqual(translate_with_plamo({"a": "Stone %s"}), {})
        self.assertEqual(post.call_count, 3)

    @patch("mod_translator.requests.post")
    def test_fails_fast_when_server_is_unavailable(self, post):
        from requests.exceptions import ConnectionError
        post.side_effect = ConnectionError("offline")
        with self.assertRaisesRegex(RuntimeError, "PLaMoサーバーに接続できません"):
            translate_with_plamo({"a": "Stone"})


if __name__ == "__main__":
    unittest.main()
