import json
import os
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mod_translator import (
    ModTranslator, build_plamo_prompt, load_plamo_glossary,
    plamo_format_is_preserved, relevant_plamo_glossary,
    resolve_plamo_model, translate_with_plamo
)


def response_with(text, finish_reason="stop"):
    response = Mock(status_code=200, text="")
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

    def test_context_history_and_glossary_follow_official_pfml3_order(self):
        context = "This text is from a Minecraft technology mod."
        prompt = build_plamo_prompt(
            "Mekanism Digital Miner", context=context,
            glossary=[{"source": "Digital Miner", "target": "デジタルマイナー"}],
            history=[("Tin Ore", "スズ鉱石")]
        )
        self.assertLess(prompt.index("<|plamo:tag|>context"), prompt.index("Tin Ore"))
        self.assertLess(prompt.index("スズ鉱石"), prompt.index("<|plamo:tag|>glossary"))
        self.assertLess(prompt.index("<|plamo:tag|>glossary"), prompt.index("<|plamo:tag|>input", prompt.index("スズ鉱石")))
        self.assertIn("<|plamo:index|>Digital Miner<|plamo:item|>デジタルマイナー", prompt)
        self.assertTrue(prompt.endswith("<|plamo:msg|>"))

    def test_glossary_json_and_source_word_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "terms.json")
            with open(path, "w", encoding="utf-8") as output:
                json.dump({"Tin": "スズ", "Digital Miner": "デジタルマイナー"}, output, ensure_ascii=False)
            glossary = load_plamo_glossary(path)
        self.assertEqual(len(glossary), 2)
        self.assertEqual(relevant_plamo_glossary("Tin Ore", glossary), [glossary[0]])
        self.assertEqual(relevant_plamo_glossary("Settings", glossary), [])
        self.assertEqual(relevant_plamo_glossary("Use Digital Miner", glossary), [glossary[1]])

    def test_numbered_placeholders_can_reorder(self):
        self.assertTrue(plamo_format_is_preserved("%1$s crafted %2$s", "%2$sを%1$sが作った"))
        self.assertFalse(plamo_format_is_preserved("%1$s crafted %2$s", "%2$sを%2$sが作った"))
        self.assertFalse(plamo_format_is_preserved("Give %s to %d", "%dに%sを与える"))
        self.assertTrue(plamo_format_is_preserved("Give %s to %d", "%sに%dを与える"))

    def test_minecraft_colors_tags_and_linebreaks(self):
        self.assertTrue(plamo_format_is_preserved("§a§C%1$s <amount>\nNext", "<amount> §C%1$s §a\n次"))
        self.assertFalse(plamo_format_is_preserved("§aHello", "§bこんにちは"))
        self.assertFalse(plamo_format_is_preserved("§AHello", "§Bこんにちは"))
        self.assertFalse(plamo_format_is_preserved("Set <amount>", "値を設定"))
        self.assertTrue(plamo_format_is_preserved("Q&A", "質問と回答"))
        self.assertTrue(plamo_format_is_preserved("R&D", "研究開発"))
        self.assertTrue(plamo_format_is_preserved("B&B", "民宿"))
        self.assertTrue(plamo_format_is_preserved("&aHello", "&bこんにちは"))
        self.assertTrue(plamo_format_is_preserved("Color&aGreen", "緑色"))
        self.assertTrue(plamo_format_is_preserved("&AColor", "&B色"))

    @patch("mod_translator.requests.get")
    def test_loaded_model_preferred_when_multiple_downloaded(self, get):
        listed = Mock()
        listed.json.return_value = {
            "data": [{"id": "plamo-3-translate-2b"}, {"id": "plamo-3-translate-8b"}]
        }
        states = Mock()
        states.json.return_value = {
            "data": [
                {"id": "plamo-3-translate-2b", "state": "not-loaded"},
                {"id": "plamo-3-translate-8b", "state": "loaded"},
            ]
        }
        get.side_effect = [listed, states]
        self.assertEqual(
            resolve_plamo_model("http://127.0.0.1:1234/v1/completions"),
            "plamo-3-translate-8b"
        )

    @patch("mod_translator.requests.post")
    def test_http_errors_abort_immediately(self, post):
        post.return_value = Mock(status_code=400, text='{"error":"Failed to load model"}')
        with self.assertRaisesRegex(RuntimeError, "Failed to load model"):
            translate_with_plamo({"a": "Stone", "b": "Wood"}, model_name="plamo-3-translate-2b")
        self.assertEqual(post.call_count, 1)

    @patch("mod_translator.time.sleep")
    @patch("mod_translator.requests.post")
    def test_truncation_increases_output_limit(self, post, sleep):
        post.side_effect = [response_with("石", "length"), response_with("石")]
        self.assertEqual(
            translate_with_plamo({"a": "Stone"}, model_name="plamo-3-translate-2b"),
            {"a": "石"}
        )
        limits = [call.kwargs["json"]["max_tokens"] for call in post.call_args_list]
        self.assertEqual(limits, [512, 1024])

    @patch("mod_translator.requests.post")
    def test_successful_previous_translation_sent_as_history(self, post):
        post.side_effect = [response_with("スズ鉱石"), response_with("スズインゴット")]
        result = translate_with_plamo(
            {"a": "Tin Ore", "b": "Tin Ingot"}, model_name="plamo-3-translate-2b",
            glossary=[{"source": "Tin", "target": "スズ"}], history_size=3
        )
        self.assertEqual(result["b"], "スズインゴット")
        second_prompt = post.call_args_list[1].kwargs["json"]["prompt"]
        self.assertIn("<|plamo:tag|>output<|plamo:key|>lang<|plamo:val|>ja<|plamo:msg|>スズ鉱石", second_prompt)
        self.assertIn("<|plamo:tag|>glossary<|plamo:index|>Tin<|plamo:item|>スズ", second_prompt)

    @patch("mod_translator.requests.post")
    def test_cache_survives_failed_request_mid_file(self, post):
        with tempfile.TemporaryDirectory() as folder:
            mods = os.path.join(folder, "mods")
            os.makedirs(mods)
            output = os.path.join(folder, "pack")
            with zipfile.ZipFile(os.path.join(mods, "demo.jar"), "w") as archive:
                archive.writestr(
                    "assets/demo/lang/en_us.json",
                    json.dumps({"item.demo.stone": "Stone", "item.demo.wood": "Wood"})
                )
            opts = SimpleNamespace(
                input=mods, output=output, engine="plamo", key=None,
                model="plamo-3-translate-2b", plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=3, gemma_only=False, force=False
            )
            from requests.exceptions import ConnectionError
            post.side_effect = [response_with("石"), ConnectionError("offline")]
            with self.assertRaisesRegex(RuntimeError, "PLaMoサーバーに接続できません"):
                ModTranslator(opts).run()
            cache_path = os.path.join(output, "plamo_cache.json")
            with open(cache_path, encoding="utf-8") as saved:
                self.assertEqual(len(json.load(saved)), 1)
            post.reset_mock()
            post.side_effect = None
            post.return_value = response_with("木")
            ModTranslator(opts).run()
            self.assertEqual(post.call_count, 1)
            translated_path = os.path.join(output, "assets", "demo", "lang", "ja_jp.json")
            with open(translated_path, encoding="utf-8") as saved:
                self.assertEqual(json.load(saved), {"item.demo.stone": "石", "item.demo.wood": "木"})

    @patch("mod_translator.requests.post")
    def test_prompt_reuses_stable_prefix_and_periodically_refreshes_history(self, post):
        post.side_effect = [response_with("翻訳") for _ in range(21)]
        samples = {"key_" + str(i): "Item " + str(i) for i in range(21)}
        translate_with_plamo(
            samples, model_name="plamo-3-translate-2b",
            context="Minecraft Mod: test.jar",
            history_size=3, history_refresh=16
        )
        prompts = [call.kwargs["json"]["prompt"] for call in post.call_args_list]
        marker = "<|plamo:tag|>input<|plamo:key|>lang<|plamo:val|>en<|plamo:msg|>Item "
        prefix_four = prompts[3].rsplit(marker, 1)[0]
        prefix_nineteen = prompts[18].rsplit(marker, 1)[0]
        prefix_twenty = prompts[19].rsplit(marker, 1)[0]
        self.assertEqual(prefix_four, prefix_nineteen)
        self.assertNotEqual(prefix_four, prefix_twenty)
        self.assertTrue(all("Minecraft Mod: test.jar" in prompt for prompt in prompts))
        self.assertEqual(post.call_count, 21)

    @patch("mod_translator.requests.post")
    def test_format_rejection_does_not_abort_mod_output(self, post):
        with tempfile.TemporaryDirectory() as folder:
            mods = os.path.join(folder, "mods")
            os.makedirs(mods)
            output = os.path.join(folder, "pack")
            original = {
                "item.demo.formatted": "§eChange defaults.§l Keep settings.",
                "item.demo.normal": "Stone"
            }
            with zipfile.ZipFile(os.path.join(mods, "demo.jar"), "w") as archive:
                archive.writestr("assets/demo/lang/en_us.json", json.dumps(original))
            opts = SimpleNamespace(
                input=mods, output=output, engine="plamo", key=None,
                model="plamo-3-translate-2b", plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=3, gemma_only=False, force=False
            )
            post.side_effect = [response_with("設定を変更。"), response_with("設定を変更。"),
                                response_with("設定を変更。"), response_with("石")]
            with patch("mod_translator.time.sleep"):
                ModTranslator(opts).run()
            result_file = os.path.join(output, "assets", "demo", "lang", "ja_jp.json")
            with open(result_file, encoding="utf-8") as saved:
                translated = json.load(saved)
            self.assertEqual(translated["item.demo.formatted"], original["item.demo.formatted"])
            self.assertEqual(translated["item.demo.normal"], "石")
            self.assertEqual(post.call_count, 4)

    @patch("mod_translator.requests.post")
    def test_nonstring_json_values_do_not_crash_output(self, post):
        with tempfile.TemporaryDirectory() as folder:
            mods = os.path.join(folder, "mods")
            os.makedirs(mods)
            output = os.path.join(folder, "pack")
            with zipfile.ZipFile(os.path.join(mods, "demo.jar"), "w") as archive:
                archive.writestr(
                    "assets/demo/lang/en_us.json",
                    json.dumps({"item.demo.stone": "Stone", "numeric": 12, "flag": True})
                )
            opts = SimpleNamespace(
                input=mods, output=output, engine="plamo", key=None,
                model="plamo-3-translate-2b", plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=3, gemma_only=False, force=False
            )
            post.return_value = response_with("石")
            ModTranslator(opts).run()
            result_file = os.path.join(output, "assets", "demo", "lang", "ja_jp.json")
            with open(result_file, encoding="utf-8") as saved:
                self.assertEqual(json.load(saved), {"item.demo.stone": "石", "numeric": 12, "flag": True})
            post.assert_called_once()

    @patch("mod_translator.requests.post")
    def test_existing_persistent_cache_is_read_after_prompt_optimization(self, post):
        with tempfile.TemporaryDirectory() as folder:
            mods = os.path.join(folder, "mods")
            os.makedirs(mods)
            output = os.path.join(folder, "pack")
            filename = "demo.jar"
            lang_path = "assets/demo/lang/en_us.json"
            with zipfile.ZipFile(os.path.join(mods, filename), "w") as archive:
                archive.writestr(lang_path, json.dumps({"item.demo.stone": "Stone"}))
            opts = SimpleNamespace(
                input=mods, output=output, engine="plamo", key=None,
                model="plamo-3-translate-2b", plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=3, gemma_only=False, force=False
            )
            previous = ModTranslator(opts)
            key = previous.plamo_cache_key(
                filename, lang_path, "item.demo.stone", "Stone",
                previous.plamo_legacy_settings_id
            )
            with open(previous.plamo_cache_file, "w", encoding="utf-8") as saved:
                json.dump({key: "石"}, saved, ensure_ascii=False)
            ModTranslator(opts).run()
            post.assert_not_called()
            result_file = os.path.join(output, "assets", "demo", "lang", "ja_jp.json")
            with open(result_file, encoding="utf-8") as saved:
                self.assertEqual(json.load(saved)["item.demo.stone"], "石")

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
