import json
import io
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from mod_translator import translate_with_plamo
from plamo_repair import (
    get_loaded_lm_studio_models, repair_plamo_translation,
    require_loaded_lm_studio_model, restore_simple_syntax, syntax_text_unchanged,
    has_japanese_translation, apply_syntax_offsets
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
    def test_repair_only_inserts_syntax_without_translating(self, post, require):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": '{"offsets":[6]}'}}]
        }
        answer = repair_plamo_translation(
            "Enchant %s levels", "エンチャントレベル", "lfm2.5",
            "http://localhost:1234/v1/chat/completions"
        )
        self.assertEqual(answer, "エンチャント%sレベル")
        require.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "lfm-instance")
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(payload["temperature"], 0)
        self.assertIn("NOT a translator", payload["messages"][0]["content"])
        self.assertIn("immutable_japanese", payload["messages"][1]["content"])
        self.assertNotIn("repaired_text", payload["response_format"]["json_schema"]["schema"]["properties"])

    @patch("plamo_repair.require_loaded_lm_studio_model")
    @patch("plamo_repair.requests.post")
    def test_simple_prefix_suffix_formats_need_no_secondary_inference(self, post, require):
        examples = [
            ("Red {0}", "赤", "赤 {0}"),
            ("§cThis operation only works in single player§r",
             "この操作はシングルプレイヤーでしか実行できません。",
             "§cこの操作はシングルプレイヤーでしか実行できません。§r"),
            ("§6Modified on %s§r", "変更日", "§6変更日 %s§r"),
            ("Anvil Cost: %s", "金床コスト", "金床コスト %s"),
            ("Available", "利用可能 %s", "利用可能")
        ]
        for source, draft, expected in examples:
            self.assertEqual(
                repair_plamo_translation(
                    source, draft, "lfm", "http://localhost:1234/v1/chat/completions"
                ), expected
            )
        post.assert_not_called()
        require.assert_not_called()

    def test_unusable_punctuation_draft_is_not_a_translation(self):
        self.assertFalse(has_japanese_translation("%s: %s  %s  %s"))
        self.assertFalse(has_japanese_translation(":"))
        self.assertFalse(has_japanese_translation("%s"))
        self.assertTrue(has_japanese_translation("赤 {0}"))
        self.assertIsNone(restore_simple_syntax("Config", "%s: %s  %s  %s"))

    def test_offset_reconstruction_rejects_invalid_positions(self):
        self.assertEqual(
            apply_syntax_offsets("エンチャントレベル", ["%s"], [6]),
            "エンチャント%sレベル"
        )
        invalid = [[], [-1], [99], [True], [6.0], ["6"]]
        for offsets in invalid:
            self.assertIsNone(apply_syntax_offsets("日本語", ["%s"], offsets))
        self.assertIsNone(apply_syntax_offsets("日本語", ["%s", "%d"], [2, 1]))
        self.assertEqual(
            apply_syntax_offsets("日本語", ["§c", "%s", "§r"], [0, 2, 3]),
            "§c日本%s語§r"
        )

    @patch("plamo_repair.require_loaded_lm_studio_model")
    @patch("plamo_repair.requests.post")
    def test_punctuation_only_output_is_never_sent_to_lfm(self, post, require):
        result = repair_plamo_translation(
            "Config", "%s: %s  %s  %s", "lfm2.5",
            "http://localhost:1234/v1/chat/completions"
        )
        self.assertIsNone(result)
        post.assert_not_called()
        require.assert_not_called()

    @patch("plamo_repair.require_loaded_lm_studio_model", return_value="loaded")
    @patch("plamo_repair.requests.post")
    def test_long_sentence_only_requests_a_placeholder_offset(self, post, require):
        source = (
            "The server does not have %s installed. Please remove the mod from "
            "your game or install it on the server as well."
        )
        japanese = (
            "サーバーにはインストールされていません。"
            "ゲームからModを削除するか、サーバーにも導入してください。"
        )
        insertion = japanese.index("インストール")
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"offsets": [insertion]})}}]
        }
        result = repair_plamo_translation(
            source, japanese, "lfm2.5", "http://localhost:1234/v1/chat/completions"
        )
        self.assertEqual(result, japanese[:insertion] + "%s" + japanese[insertion:])
        self.assertIn('"immutable_japanese":', post.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertNotIn("repaired_text", post.call_args.kwargs["json"]["response_format"]["json_schema"]["schema"]["properties"])

    @patch("mod_translator.require_loaded_lm_studio_model", return_value="loaded")
    def test_old_punctuation_only_repair_cache_is_ignored(self, loaded):
        import tempfile
        from types import SimpleNamespace
        from mod_translator import ModTranslator

        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(
                input=folder, output=folder, engine="plamo", key=None,
                model="plamo-3-translate-0.8b",
                plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=3,
                gemma_only=False, force=False, repair_model="lfm2.5-1.2b",
                repair_api_url="http://127.0.0.1:1234/v1/chat/completions",
                model_load_policy="wait"
            )
            translator = ModTranslator(args)
            translator.save_plamo_repair_translation(
                "broken.jar", "assets/broken/lang/en_us.json", "config", "Config", ":"
            )
            self.assertIsNone(ModTranslator(args).get_plamo_translation(
                "broken.jar", "assets/broken/lang/en_us.json", "config", "Config"
            ))

    @patch("plamo_repair.require_loaded_lm_studio_model", return_value="loaded")
    @patch("plamo_repair.requests.post")
    def test_schema_cannot_make_lfm_rewrite_the_japanese_draft(self, post, require):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": '{"offsets":[6],"repaired_text":"新訳に変更"}'}}]
        }
        result = repair_plamo_translation(
            "Enchant %s levels", "エンチャントレベル", "lfm2.5",
            "http://localhost:1234/v1/chat/completions"
        )
        self.assertEqual(result, "エンチャント%sレベル")

    @patch("mod_translator.require_loaded_lm_studio_model", return_value="ok")
    @patch("mod_translator.repair_plamo_translation")
    @patch("mod_translator.requests.post", return_value=complete("%s: %s  %s  %s"))
    def test_pipeline_drops_nonsensical_draft_before_repair_queue(self, post, repair, loaded):
        result = translate_with_plamo(
            {"config": "Config", "disable": "Disable Mod"},
            model_name="plamo-3-translate-0.8b", repair_model="lfm2.5"
        )
        self.assertEqual(result, {})
        repair.assert_not_called()
        self.assertEqual(post.call_count, 2)

    @patch("plamo_repair.require_loaded_lm_studio_model", return_value="loaded")
    @patch("plamo_repair.requests.post")
    def test_secondary_retranslation_is_rejected_even_with_valid_format(self, post, require):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": '{"repaired_text":"処理済みフレーム数: %1$d / %2$d"}'}}]
        }
        original = "Обработано кадров: %1$d / %2$d"
        rejected = "OpenEXRファイルシリーズ"
        self.assertIsNone(
            repair_plamo_translation(
                original, rejected, "lfm2.5",
                "http://localhost:1234/v1/chat/completions"
            )
        )
        self.assertFalse(syntax_text_unchanged(rejected, "処理済みフレーム数: %1$d / %2$d"))
        post.assert_called_once()

    @patch("plamo_repair.require_loaded_lm_studio_model", return_value="loaded")
    @patch("plamo_repair.requests.post")
    def test_valid_syntax_repair_cannot_change_existing_japanese(self, post, require):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": '{"repaired_text":"追加エンチャント%sレベル"}'}}]
        }
        self.assertIsNone(repair_plamo_translation(
            "Enchant %s levels", "エンチャントレベル", "lfm2.5",
            "http://localhost:1234/v1/chat/completions"
        ))

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
    @patch("mod_translator.repair_plamo_translation", side_effect=["北", None])
    @patch("mod_translator.requests.post")
    def test_repair_details_and_final_summary_are_visible(self, post, repair, loaded):
        post.side_effect = [complete("北 %s"), complete("東 %s")]
        output = io.StringIO()
        with redirect_stdout(output):
            result = translate_with_plamo(
                {"north": "North", "east": "East"},
                model_name="plamo-3-translate-0.8b", repair_model="lfm2.5-350m"
            )
        self.assertEqual(result, {"north": "北"})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(repair.call_count, 2)
        self.assertIn('修復依頼[1件目]', output.getvalue())
        self.assertIn('修復[1件成功]', output.getvalue())
        self.assertIn('原文: "North"', output.getvalue())
        self.assertIn('PLaMoの失敗訳:', output.getvalue())
        self.assertIn('修復後: "北"', output.getvalue())
        self.assertIn('修復[失敗・原文維持]', output.getvalue())
        self.assertIn('修復集計: 依頼 2件 / 成功 1件 / 失敗・原文維持 1件', output.getvalue())
        self.assertEqual(loaded.call_args_list[0].args[2], "wait")

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

    @patch("mod_translator.require_loaded_lm_studio_model", return_value="ok")
    @patch("mod_translator.repair_plamo_translation", return_value="翡翠 %s")
    @patch("mod_translator.requests.post", return_value=complete("石 %s %s"))
    def test_translation_pipeline_rejects_secondary_japanese_rewrite(self, post, repair, loaded):
        result = translate_with_plamo(
            {"a": "Stone %s"}, model_name="plamo-3-translate-0.8b",
            repair_model="lfm2.5"
        )
        self.assertEqual(result, {})
        repair.assert_called_once()

    @patch("mod_translator.require_loaded_lm_studio_model", return_value="loaded")
    def test_repair_cache_tracks_selected_model(self, loaded):
        import tempfile
        from types import SimpleNamespace
        from mod_translator import ModTranslator

        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(
                input=folder, output=folder, engine="plamo", key=None,
                model="plamo-3-translate-0.8b",
                plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=3,
                gemma_only=False, force=False,
                repair_model="lfm2.5-1.2b",
                repair_api_url="http://127.0.0.1:1234/v1/chat/completions",
                model_load_policy="error"
            )
            translator = ModTranslator(args)
            translator.save_plamo_repair_translation(
                "demo.jar", "assets/demo/lang/en_us.json",
                "cost", "Anvil Cost: %s", "金床コスト: %s"
            )
            self.assertEqual(
                ModTranslator(args).get_plamo_translation(
                    "demo.jar", "assets/demo/lang/en_us.json", "cost", "Anvil Cost: %s"
                ),
                "金床コスト: %s"
            )
            args.repair_model = "larger-model"
            self.assertIsNone(
                ModTranslator(args).get_plamo_translation(
                    "demo.jar", "assets/demo/lang/en_us.json", "cost", "Anvil Cost: %s"
                )
            )

    @patch("mod_translator.require_loaded_lm_studio_model")
    def test_generic_llm_constructor_does_not_enable_repair(self, loaded):
        import tempfile
        from types import SimpleNamespace
        from mod_translator import ModTranslator

        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(
                input=folder, output=folder, engine="lmstudio", key=None,
                model="regular-llm", plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_history=3,
                gemma_only=False, force=False, repair_model="lfm2.5"
            )
            translator = ModTranslator(args)
            self.assertIsNone(translator.repair_model)
            loaded.assert_not_called()

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
