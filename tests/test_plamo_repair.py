import json
import threading
import unittest
from unittest.mock import Mock, patch

from mod_translator import translate_with_plamo
from plamo_repair import (
    get_loaded_lm_studio_models, repair_plamo_translation,
    require_loaded_lm_studio_model
)


def complete(text):
    response = Mock(status_code=200, text="")
    response.json.return_value = {
        "choices": [{"text": text, "finish_reason": "stop"}]
    }
    return response


class PlamoSecondaryRepairTests(unittest.TestCase):
    @patch("plamo_repair.requests.get")
    def test_native_v1_only_returns_loaded_model_instances(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {
            "models": [
                {
                    "type": "llm", "key": "publisher/translation",
                    "loaded_instances": [{"id": "plamo-loaded"}]
                },
                {
                    "type": "llm", "key": "publisher/repair",
                    "loaded_instances": [{"id": "lfm-loaded"}]
                },
                {
                    "type": "llm", "key": "publisher/unloaded",
                    "loaded_instances": []
                }
            ]
        }
        loaded = get_loaded_lm_studio_models("http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual(loaded["plamo-loaded"], "plamo-loaded")
        self.assertEqual(loaded["publisher/translation"], "plamo-loaded")
        self.assertEqual(loaded["lfm-loaded"], "lfm-loaded")
        self.assertNotIn("publisher/unloaded", loaded)
        get.assert_called_once_with("http://127.0.0.1:1234/api/v1/models", timeout=10)

    @patch("plamo_repair.requests.get")
    def test_native_v0_fallback_uses_only_loaded_entries(self, get):
        get.side_effect = [
            Mock(status_code=404),
            Mock(status_code=200, json=Mock(return_value={
                "data": [
                    {"id": "lfm-loaded", "state": "loaded"},
                    {"id": "other", "state": "not-loaded"}
                ]
            }))
        ]
        self.assertEqual(
            get_loaded_lm_studio_models("http://localhost:1234/v1/chat/completions"),
            {"lfm-loaded": "lfm-loaded"}
        )
        self.assertEqual(get.call_count, 2)

    @patch("plamo_repair.requests.post")
    @patch("plamo_repair.requests.get")
    def test_missing_repair_model_fails_without_auto_loading(self, get, post):
        get.return_value = Mock(status_code=200, json=Mock(return_value={"models": []}))
        with self.assertRaisesRegex(RuntimeError, "手動ロード"):
            require_loaded_lm_studio_model(
                "lfm2.5", "http://localhost:1234/v1/chat/completions", "error"
            )
        post.assert_not_called()
        get.assert_called_once()

    @patch("plamo_repair.time.sleep")
    @patch("plamo_repair.requests.get")
    def test_wait_policy_resumes_after_manual_model_load(self, get, sleep):
        get.side_effect = [
            Mock(status_code=200, json=Mock(return_value={"models": []})),
            Mock(status_code=200, json=Mock(return_value={
                "models": [{
                    "type": "llm", "key": "lfm2.5",
                    "loaded_instances": [{"id": "lfm-instance"}]
                }]
            }))
        ]
        self.assertEqual(
            require_loaded_lm_studio_model(
                "lfm2.5", "http://localhost:1234/v1/chat/completions",
                "wait", poll_seconds=0
            ), "lfm-instance"
        )
        sleep.assert_called_once_with(0)

    @patch("plamo_repair.require_loaded_lm_studio_model", return_value="lfm-instance")
    @patch("plamo_repair.requests.post")
    def test_repair_uses_selected_model_and_json_schema(self, post, require):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": '{"translation":"金床コスト: %s"}'}}]
        }
        answer = repair_plamo_translation(
            "Anvil Cost: %s", "金床コスト", "lfm2.5",
            "http://localhost:1234/v1/chat/completions"
        )
        self.assertEqual(answer, "金床コスト: %s")
        require.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "lfm-instance")
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(payload["temperature"], 0)

    @patch("mod_translator.require_loaded_lm_studio_model", return_value="ok")
    @patch("mod_translator.repair_plamo_translation")
    @patch("mod_translator.requests.post")
    def test_translation_continues_while_secondary_model_repairs(self, post, repair, loaded):
        next_translation = threading.Event()

        def completion(url, json, timeout):
            if "Grass" in json["prompt"]:
                next_translation.set()
                return complete("草")
            return complete("石 %s %s")

        def background_repair(*args):
            if not next_translation.wait(3):
                raise RuntimeError("PLaMoが次の翻訳を開始していません")
            return "石 %s"

        post.side_effect = completion
        repair.side_effect = background_repair
        translated, repaired = [], []
        result = translate_with_plamo(
            {"first": "Stone %s", "second": "Grass"},
            model_name="plamo-3-translate-0.8b",
            repair_model="lfm2.5",
            on_translation=lambda k, src, dst: translated.append((k, dst)),
            on_repair_translation=lambda k, src, dst: repaired.append((k, dst))
        )
        self.assertEqual(result, {"first": "石 %s", "second": "草"})
        self.assertEqual(translated, [("second", "草")])
        self.assertEqual(repaired, [("first", "石 %s")])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(repair.call_count, 1)

    @patch("mod_translator.require_loaded_lm_studio_model", return_value="ok")
    @patch("mod_translator.repair_plamo_translation", return_value="石")
    @patch("mod_translator.requests.post", return_value=complete("石 %s %s"))
    def test_repair_cannot_remove_original_format_tokens(self, post, repair, loaded):
        result = translate_with_plamo(
            {"a": "Stone %s"}, model_name="plamo-3-translate-0.8b",
            repair_model="lfm2.5"
        )
        self.assertEqual(result, {})
        self.assertEqual(repair.call_count, 1)

    @patch("mod_translator.require_loaded_lm_studio_model")
    @patch("mod_translator.requests.post")
    def test_mode_without_repair_keeps_existing_behavior(self, post, loaded):
        post.return_value = complete("草")
        self.assertEqual(
            translate_with_plamo({"a": "Grass"}, model_name="plamo-3-translate-0.8b"),
            {"a": "草"}
        )
        loaded.assert_not_called()


if __name__ == "__main__":
    unittest.main()
