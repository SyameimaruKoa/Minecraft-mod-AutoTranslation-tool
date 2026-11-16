import json
import unittest
from unittest.mock import Mock, patch

from mod_translator import (
    ModelSelector, get_available_gemini_models, get_prioritized_models,
    translate_with_gemini
)


def response_for(values):
    return Mock(
        status_code=200,
        json=Mock(return_value={"candidates": [{
            "content": {"parts": [
                {"thought": True, "text": "internal"},
                {"text": json.dumps(values, ensure_ascii=False)}
            ]}
        }]}),
    )


class TestGemini(unittest.TestCase):
    @patch("mod_translator.requests.get")
    def test_model_discovery_filters_capabilities_and_pages(self, get):
        get.side_effect = [
            Mock(status_code=200, json=Mock(return_value={
                "models": [
                    {"name": "models/gemini-3.7-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-3.1-flash-image", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]}
                ],
                "nextPageToken": "page-two"
            })),
            Mock(status_code=200, json=Mock(return_value={
                "models": [
                    {"name": "models/gemma-4-26b-a4b-it", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-3.7-flash", "supportedGenerationMethods": ["generateContent"]}
                ]
            }))
        ]
        models = get_available_gemini_models("private-key")
        self.assertEqual(models, ["gemini-3.7-flash", "gemini-3.1-flash-image", "gemma-4-26b-a4b-it"])
        self.assertEqual(get.call_count, 2)
        for call in get.call_args_list:
            self.assertNotIn("private-key", call.args[0])
            self.assertEqual(call.kwargs["headers"]["x-goog-api-key"], "private-key")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["pageToken"], "page-two")

    @patch("mod_translator.get_available_gemini_models")
    def test_auto_selection_is_generic_and_pro_is_manual(self, listing):
        listing.return_value = [
            "gemini-3.1-flash-image", "gemini-3.8-flash-preview",
            "gemini-3.7-flash", "gemini-3.6-flash",
            "gemini-3.1-flash-lite", "gemini-3.1-pro-preview",
            "gemma-4-26b-a4b-it"
        ]
        selected = get_prioritized_models("key")
        self.assertEqual(selected, [
            "gemini-3.7-flash", "gemini-3.6-flash",
            "gemini-3.1-flash-lite", "gemma-4-26b-a4b-it",
            "gemini-3.8-flash-preview"
        ])
        self.assertEqual(get_prioritized_models("key", gemma_only=True), ["gemma-4-26b-a4b-it"])

    @patch("mod_translator.get_available_gemini_models", return_value=[])
    def test_missing_models_fail_closed(self, listing):
        with self.assertRaisesRegex(RuntimeError, "APIから返されません"):
            get_prioritized_models("key")

    @patch("mod_translator.requests.get")
    def test_listing_http_errors_do_not_invent_model_names(self, get):
        get.return_value = Mock(status_code=403)
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            get_available_gemini_models("key")

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_removed_model_switches_and_keeps_key_out_of_url(self, post, sleep):
        observed = []

        def respond(url, headers, json, timeout):
            observed.append((url, headers))
            if "gemini-99-flash" in url:
                return Mock(status_code=404, json=Mock(return_value={"error": {"message": "Not found"}}))
            return response_for({"test": "石 %s"})

        post.side_effect = respond
        selector = ModelSelector(["gemini-99-flash", "gemini-3.7-flash"])
        result = translate_with_gemini({"test": "Stone %s"}, "private-key", selector)
        self.assertEqual(result, {"test": "石 %s"})
        self.assertEqual(post.call_count, 2)
        self.assertNotIn("private-key", observed[0][0])
        self.assertTrue(all(h["x-goog-api-key"] == "private-key" for _, h in observed))

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_format_marker_loss_is_retried(self, post, sleep):
        post.side_effect = [response_for({"test": "石"}), response_for({"test": "石 %s"})]
        result = translate_with_gemini(
            {"test": "Stone %s"}, "key", ModelSelector(["gemini-3.7-flash"])
        )
        self.assertEqual(result, {"test": "石 %s"})
        self.assertEqual(post.call_count, 2)

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_repeated_invalid_json_switches_models(self, post, sleep):
        def respond(url, headers, json, timeout):
            if "gemini-3.8-flash" in url:
                return response_for({"test": "石"})
            return response_for({"test": "石 %s"})
        post.side_effect = respond
        result = translate_with_gemini(
            {"test": "Stone %s"}, "key",
            ModelSelector(["gemini-3.8-flash", "gemini-3.7-flash"])
        )
        self.assertEqual(result, {"test": "石 %s"})
        self.assertEqual(post.call_count, 4)

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_429_is_finite_without_fallback(self, post, sleep):
        post.return_value = Mock(status_code=429, headers={"Retry-After": "0"})
        with self.assertRaisesRegex(RuntimeError, "すべて失敗"):
            translate_with_gemini(
                {"test": "Stone"}, "key", ModelSelector(["gemini-3.7-flash"])
            )
        self.assertEqual(post.call_count, 3)

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_json_mode_rejection_retries_without_generation_config(self, post, sleep):
        post.side_effect = [
            Mock(status_code=400, json=Mock(return_value={"error": {"message": "JSON mode not supported"}})),
            response_for({"test": "石"})
        ]
        result = translate_with_gemini(
            {"test": "Stone"}, "key", ModelSelector(["gemma-4-26b-a4b-it"])
        )
        self.assertEqual(result, {"test": "石"})
        self.assertEqual(post.call_count, 2)
        self.assertIn("generationConfig", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("generationConfig", post.call_args_list[1].kwargs["json"])

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_read_timeout_splits_without_losing_or_repeating_keys(self, post, sleep):
        from requests.exceptions import ReadTimeout
        calls = []

        def respond(url, headers, json, timeout):
            batch = __import__("json").loads(json["contents"][0]["parts"][0]["text"].split("\n\n", 1)[1])
            calls.append(list(batch))
            self.assertEqual(timeout, (10, 45))
            if len(batch) > 1:
                raise ReadTimeout("read timeout")
            return response_for({key: value + "訳" for key, value in batch.items()})

        post.side_effect = respond
        source = {"a": "Stone", "b": "Grass", "c": "Coal", "d": "Iron"}
        actual = translate_with_gemini(source, "key", ModelSelector(["gemini-3.8-flash"]))
        self.assertEqual(actual, {key: value + "訳" for key, value in source.items()})
        self.assertEqual(post.call_count, 7)
        self.assertEqual([batch[0] for batch in calls if len(batch) == 1], list(source))

    @patch("mod_translator.requests.post")
    def test_flash_requests_low_thinking(self, post):
        post.return_value = response_for({"test": "石"})
        translate_with_gemini({"test": "Stone"}, "key", ModelSelector(["gemini-3.8-flash"]))
        config = post.call_args.kwargs["json"]["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "low"})

    @patch("mod_translator.requests.post")
    def test_25_flash_disables_thinking(self, post):
        post.return_value = response_for({"test": "石"})
        translate_with_gemini({"test": "Stone"}, "key", ModelSelector(["gemini-2.5-flash"]))
        config = post.call_args.kwargs["json"]["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingBudget": 0})

    @patch("mod_translator.requests.post")
    def test_batch_size_caps_request_character_budget(self, post):
        from mod_translator import _gemini_batches
        batches = _gemini_batches({"a": "A" * 1400, "b": "B" * 1400, "c": "C"}, 8)
        self.assertEqual([list(batch) for batch in batches], [["a"], ["b", "c"]])

    @patch("mod_translator.requests.post")
    def test_invalid_api_key_stops_immediately(self, post):
        post.return_value = Mock(status_code=401)
        with self.assertRaises(PermissionError):
            translate_with_gemini(
                {"test": "Stone"}, "key", ModelSelector(["gemini-3.7-flash"])
            )
        self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
