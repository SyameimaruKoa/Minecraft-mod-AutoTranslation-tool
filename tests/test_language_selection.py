import json
import os
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mod_translator import (
    ModTranslator, build_plamo_prompt, extract_lang_files,
    language_code_from_path, translate_with_plamo
)


class LanguageSelectionTests(unittest.TestCase):
    def make_jar(self, folder, files):
        path = os.path.join(folder, "example.jar")
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in files.items():
                archive.writestr(
                    name, json.dumps(data, ensure_ascii=False)
                    if name.endswith(".json") else data
                )
        return path

    def test_largest_non_japanese_locale_per_namespace(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.make_jar(folder, {
                "assets/demo/lang/en_us.json": {"a": "Stone", "b": "Wood"},
                "assets/demo/lang/fr_fr.json": {
                    "a": "Pierre", "b": "Bois", "c": "Terre"
                },
                "assets/demo/lang/ja_jp.json": {
                    "a": "石", "b": "木", "c": "土", "d": "水"
                },
                "assets/other/lang/en_us.json": {"a": "Hello"},
                "assets/other/lang/de_de.json": {
                    "a": "Hallo", "b": "Welt"
                }
            })
            files = extract_lang_files(archive)
            self.assertEqual(set(files), {
                "assets/demo/lang/fr_fr.json",
                "assets/other/lang/de_de.json"
            })
            self.assertEqual(len(files["assets/demo/lang/fr_fr.json"]), 3)

    def test_equal_count_prefers_english_and_json(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.make_jar(folder, {
                "assets/demo/lang/de_de.json": {"a": "Stein"},
                "assets/demo/lang/en_US.lang": "a=Stone\n",
                "assets/demo/lang/en_us.json": {"a": "Stone"},
            })
            self.assertEqual(
                list(extract_lang_files(archive)),
                ["assets/demo/lang/en_us.json"]
            )

    def test_counts_translatable_strings_not_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.make_jar(folder, {
                "assets/demo/lang/en_us.json": {
                    "a": "Stone", "b": "Wood"
                },
                "assets/demo/lang/de_de.json": {
                    "a": "Stein", "language.name": "Deutsch",
                    "numeric": 12, "flag": True
                }
            })
            self.assertEqual(
                list(extract_lang_files(archive)),
                ["assets/demo/lang/en_us.json"]
            )

    def test_legacy_lang_and_shader_locales(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.make_jar(folder, {
                "assets/demo/lang/en_US.lang": "a=Stone\n",
                "assets/demo/lang/ko_KR.lang": "a=돌\nb=나무\n",
                "shaders/lang/en_US.lang": "a=Water\n",
                "shaders/lang/ru_RU.lang": "a=Вода\nb=Камень\n"
            })
            self.assertEqual(
                list(extract_lang_files(archive)),
                ["assets/demo/lang/ko_KR.lang", "shaders/lang/ru_RU.lang"]
            )
            self.assertEqual(
                list(extract_lang_files(archive, is_shader_mode=True)),
                ["assets/demo/lang/ko_KR.lang", "shaders/lang/ru_RU.lang"]
            )

    def test_source_language_codes(self):
        cases = {
            "assets/mod/lang/en_us.json": "en",
            "assets/mod/lang/fr_fr.json": "fr",
            "assets/mod/lang/zh_cn.json": "zh-hans",
            "assets/mod/lang/zh_tw.json": "zh-hant",
            "assets/mod/lang/ko_KR.lang": "ko",
            "assets/mod/lang/pt_br.json": "pt",
        }
        for path, expected in cases.items():
            self.assertEqual(language_code_from_path(path), expected)

    def test_non_english_prompt_and_history_use_source_language(self):
        prompt = build_plamo_prompt(
            "Bonjour", history=[("Salut", "こんにちは")], source_lang="fr"
        )
        self.assertEqual(
            prompt.count("<|plamo:key|>lang<|plamo:val|>fr<|plamo:msg|>"), 2
        )
        self.assertIn(
            "<|plamo:tag|>output<|plamo:key|>lang<|plamo:val|>ja",
            prompt
        )

    @patch("mod_translator.requests.post")
    def test_multiline_translation_uses_source_language(self, post):
        post.return_value = Mock(status_code=200, text="", json=Mock(
            return_value={"choices": [
                {"text": "こんにちは<mc_line_0>世界", "finish_reason": "stop"}
            ]}
        ))
        result = translate_with_plamo(
            {"a": "Bonjour\nMonde"}, model_name="plamo-3-translate-2b",
            source_lang="fr", history_size=0
        )
        self.assertEqual(result, {"a": "こんにちは\n世界"})
        self.assertIn(
            "<|plamo:key|>lang<|plamo:val|>fr<|plamo:msg|>",
            post.call_args.kwargs["json"]["prompt"]
        )

    @patch("mod_translator.requests.post")
    def test_mod_runner_uses_selected_locale_in_plamo_prompt(self, post):
        with tempfile.TemporaryDirectory() as folder:
            mods = os.path.join(folder, "mods")
            output = os.path.join(folder, "output")
            os.makedirs(mods)
            self.make_jar(mods, {
                "assets/demo/lang/en_us.json": {"a": "Stone"},
                "assets/demo/lang/zh_cn.json": {"a": "石头", "b": "木材"}
            })
            post.return_value = Mock(status_code=200, text="", json=Mock(
                return_value={"choices": [
                    {"text": "日本語", "finish_reason": "stop"}
                ]}
            ))
            options = SimpleNamespace(
                input=mods, output=output, engine="plamo", key=None,
                model="plamo-3-translate-8b",
                plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=0,
                gemma_only=False, force=False
            )
            ModTranslator(options).run()
            self.assertEqual(post.call_count, 2)
            for call in post.call_args_list:
                self.assertIn(
                    "<|plamo:key|>lang<|plamo:val|>zh-hans<|plamo:msg|>",
                    call.kwargs["json"]["prompt"]
                )
            with open(
                os.path.join(output, "assets", "demo", "lang", "ja_jp.json"),
                encoding="utf-8"
            ) as translated:
                self.assertEqual(
                    json.load(translated), {"a": "日本語", "b": "日本語"}
                )

    def test_non_english_cache_key_does_not_reuse_old_entries(self):
        translator = ModTranslator.__new__(ModTranslator)
        translator.plamo_settings_id = "settings"
        english = translator.plamo_cache_key(
            "mod.jar", "assets/demo/lang/en_us.json", "a", "Stone"
        )
        french = translator.plamo_cache_key(
            "mod.jar", "assets/demo/lang/fr_fr.json", "a", "Pierre"
        )
        self.assertEqual(len(json.loads(english)), 5)
        self.assertEqual(json.loads(french)[-1], "fr")


if __name__ == "__main__":
    unittest.main()
