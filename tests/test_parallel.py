import json
import io
from contextlib import redirect_stdout
import threading
import time
import unittest
from unittest.mock import Mock, patch

from mod_translator import (
    ModelSelector, translate_local_llm, translate_with_gemini,
    translate_with_plamo
)
from translation_parallel import (
    SharedRequestPacer, SynchronizedModelSelector, translate_parallel_batches
)


class ParallelTranslationTests(unittest.TestCase):
    def test_parallel_executor_runs_concurrently_and_preserves_input_order(self):
        barrier = threading.Barrier(2, timeout=3)

        def translate(batch):
            barrier.wait()
            if "a" in batch:
                time.sleep(0.02)
            return {key: value + "訳" for key, value in batch.items()}

        texts = {"a": "石", "b": "草"}
        result = translate_parallel_batches(texts, 2, 1, translate, "Test")
        self.assertEqual(result, {"a": "石訳", "b": "草訳"})
        self.assertEqual(list(result), ["a", "b"])

    def test_parallel_executor_rejects_invalid_workers(self):
        with self.assertRaises(ValueError):
            translate_parallel_batches({"a": "A"}, 0, 1, lambda batch: batch, "Test")
        with self.assertRaises(ValueError):
            translate_parallel_batches({"a": "A"}, 2, 0, lambda batch: batch, "Test")

    def test_parallel_executor_keeps_successes_and_omits_missing_keys(self):
        result = translate_parallel_batches(
            {"a": "A", "b": "B", "c": "C"},
            2, 1, lambda batch: {"a": "甲"} if "a" in batch else {},
            "Test"
        )
        self.assertEqual(result, {"a": "甲"})

    @patch("mod_translator.requests.post")
    def test_local_ollama_requests_are_parallel(self, post):
        barrier = threading.Barrier(2, timeout=3)

        def respond(url, json, timeout):
            barrier.wait()
            sent = __import__("json").loads(json["messages"][0]["content"].split("\n", 1)[1])
            translated = {key: "訳" + value for key, value in sent.items()}
            return Mock(
                status_code=200, json=Mock(return_value={
                    "message": {"content": __import__("json").dumps(translated, ensure_ascii=False)}
                })
            )

        post.side_effect = respond
        texts = {f"key{i}": f"Text{i}" for i in range(21)}
        result = translate_local_llm(texts, "ollama", "test-model", workers=2)
        self.assertEqual(len(result), 21)
        self.assertEqual(list(result), list(texts))
        self.assertEqual(post.call_count, 2)

    @patch("mod_translator.requests.post")
    def test_local_lm_studio_requests_are_parallel(self, post):
        barrier = threading.Barrier(2, timeout=3)

        def respond(url, json, timeout):
            barrier.wait()
            sent = __import__("json").loads(json["messages"][0]["content"].split("\n", 1)[1])
            translated = {key: "訳" + value for key, value in sent.items()}
            return Mock(
                status_code=200, json=Mock(return_value={
                    "choices": [{"message": {
                        "content": __import__("json").dumps(translated, ensure_ascii=False)
                    }}]
                })
            )

        post.side_effect = respond
        result = translate_local_llm(
            {f"k{i}": f"v{i}" for i in range(21)}, "lmstudio", "test", workers=2
        )
        self.assertEqual(len(result), 21)
        self.assertEqual(post.call_count, 2)

    @patch("mod_translator.requests.post")
    def test_plamo_parallel_requests_and_serialized_callbacks(self, post):
        barrier = threading.Barrier(2, timeout=3)
        callback_lock = threading.Lock()
        callback_keys = []

        def respond(url, json, timeout):
            barrier.wait()
            input_text = json["prompt"].rsplit("<|plamo:tag|>input", 1)[-1].split("<|plamo:msg|>", 1)[1].split("<|plamo:tag|>output", 1)[0]
            return Mock(status_code=200, json=Mock(return_value={
                "choices": [{"text": f"訳{input_text}", "finish_reason": "stop"}]
            }))

        def callback(key, source, translated):
            self.assertTrue(callback_lock.acquire(blocking=False))
            try:
                callback_keys.append(key)
                time.sleep(0.01)
            finally:
                callback_lock.release()

        post.side_effect = respond
        texts = {"a": "Stone", "b": "Stone", "c": "Grass"}
        result = translate_with_plamo(
            texts, model_name="plamo-3-translate-0.8b",
            history_size=0, workers=2, on_translation=callback
        )
        self.assertEqual(result, {"a": "訳Stone", "b": "訳Stone", "c": "訳Grass"})
        self.assertCountEqual(callback_keys, ["a", "b", "c"])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(list(result), list(texts))

    @patch("mod_translator.require_loaded_lm_studio_model", return_value="loaded")
    @patch("mod_translator.requests.post")
    def test_plamo_parallel_shows_one_zero_repair_summary_and_unique_count(self, post, loaded):
        barrier = threading.Barrier(2, timeout=3)

        def respond(url, json, timeout):
            barrier.wait()
            original = json["prompt"].rsplit("<|plamo:tag|>input", 1)[-1]
            original = original.split("<|plamo:msg|>", 1)[1].split("<|plamo:tag|>output", 1)[0]
            return Mock(status_code=200, json=Mock(return_value={
                "choices": [{"text": "訳" + original, "finish_reason": "stop"}]
            }))

        post.side_effect = respond
        output = io.StringIO()
        with redirect_stdout(output):
            result = translate_with_plamo(
                {"a": "Stone", "b": "Stone", "c": "Grass"},
                model_name="plamo-3-translate-0.8b", workers=2,
                history_size=0, repair_model="lfm2.5"
            )
        self.assertEqual(result, {"a": "訳Stone", "b": "訳Stone", "c": "訳Grass"})
        rendered = output.getvalue()
        self.assertIn("重複を除いた推論対象: 2 項目", rendered)
        self.assertIn("重複 1 項目", rendered)
        self.assertEqual(rendered.count("修復集計:"), 1)
        self.assertIn("修復集計: 依頼 0件 / 成功 0件 / 失敗・原文維持 0件", rendered)
        self.assertIn("進捗: 1/2 (50.0%)", rendered)
        self.assertIn("進捗: 2/2 (100.0%)", rendered)
        self.assertNotIn("並列進捗", rendered)
        self.assertNotIn("0分", rendered)

    @patch("mod_translator.require_loaded_lm_studio_model", return_value="loaded")
    @patch("mod_translator.repair_plamo_translation")
    @patch("mod_translator.requests.post")
    def test_plamo_parallel_aggregates_repairs_with_sequential_log_numbering(
        self, post, repair, loaded
    ):
        barrier = threading.Barrier(2, timeout=3)

        def respond(url, json, timeout):
            barrier.wait()
            return Mock(status_code=200, json=Mock(return_value={
                "choices": [{"text": "訳", "finish_reason": "stop"}]
            }))

        def repaired(source, draft, *args):
            return "石 %s" if source.startswith("Stone") else "草 %s"

        post.side_effect = respond
        repair.side_effect = repaired
        output = io.StringIO()
        with redirect_stdout(output):
            result = translate_with_plamo(
                {"a": "Stone %s", "b": "Grass %s"},
                model_name="plamo-3-translate-0.8b",
                history_size=0, workers=2, repair_model="lfm2.5"
            )
        self.assertEqual(result, {"a": "石 %s", "b": "草 %s"})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(repair.call_count, 2)
        rendered = output.getvalue()
        self.assertEqual(rendered.count("修復集計:"), 1)
        self.assertIn("修復集計: 依頼 2件 / 成功 2件 / 失敗・原文維持 0件", rendered)
        self.assertEqual(rendered.count("修復依頼[1件目]"), 1)
        self.assertEqual(rendered.count("修復依頼[2件目]"), 1)
        self.assertEqual(rendered.count("修復[1件成功]"), 1)
        self.assertEqual(rendered.count("修復[2件成功]"), 1)
        self.assertNotIn("未完了結果を回収中", rendered)

    @patch("translation_parallel.SharedRequestPacer.wait")
    @patch("mod_translator.requests.post")
    def test_gemini_parallel_batches_share_model_selector(self, post, pace):
        barrier = threading.Barrier(2, timeout=3)

        def respond(url, headers, json, timeout):
            barrier.wait()
            payload = __import__("json").loads(json["contents"][0]["parts"][0]["text"].split("\n\n", 1)[1])
            translated = {key: value + "訳" for key, value in payload.items()}
            return Mock(status_code=200, json=Mock(return_value={
                "candidates": [{
                    "content": {"parts": [{"text": __import__("json").dumps(translated, ensure_ascii=False)}]}
                }]
            }))

        post.side_effect = respond
        selector = ModelSelector(["gemini-2.5-flash"])
        texts = {"a": "A", "b": "B", "c": "C", "d": "D"}
        result = translate_with_gemini(texts, "api-test", selector, workers=2)
        self.assertEqual(result, {key: value + "訳" for key, value in texts.items()})
        self.assertEqual(list(result), list(texts))
        self.assertEqual(post.call_count, 2)
        self.assertEqual(pace.call_count, 2)

    @patch("translation_parallel.time.sleep")
    @patch("translation_parallel.time.monotonic", return_value=100)
    def test_gemini_global_pacer_spaces_requests(self, monotonic, sleep):
        pacer = SharedRequestPacer()
        pacer.wait("gemini-2.5-flash", 6.2)
        sleep.assert_not_called()
        pacer.wait("gemini-2.5-flash", 6.2)
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 6.2)

    def test_selector_ignores_stale_model_completion(self):
        selector = ModelSelector(["first", "second"])
        concurrent = SynchronizedModelSelector(selector)
        concurrent.get_current_model()
        selector.report_failure()
        selector.report_failure()
        selector.report_failure()
        self.assertEqual(selector.get_current_model(), "second")
        concurrent.report_success()
        self.assertEqual(selector.get_current_model(), "second")


if __name__ == "__main__":
    unittest.main()
