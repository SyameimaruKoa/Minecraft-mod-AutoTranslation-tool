import json
import os
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mod_translator import ModTranslator


class PlamoSourceCacheReuseTests(unittest.TestCase):
    def make_args(self, mods, output, model, context=""):
        return SimpleNamespace(
            input=mods, output=output, engine="plamo", key=None,
            model=model, plamo_models=None, plamo_hosts=None,
            plamo_api_url="http://127.0.0.1:1234/v1/completions",
            plamo_form="plain", plamo_glossary=None, plamo_context=context,
            plamo_context_file=None, plamo_history=0, workers=1,
            gemma_only=False, force=False
        )

    def make_mod(self, directory, source):
        path = os.path.join(directory, "example.jar")
        with zipfile.ZipFile(path, "w") as archive:
            for filename, values in {
                "assets/demo/lang/en_us.json": {"a": source, "b": "Iron"},
                "assets/demo/lang/ja_jp.json": {"b": "鉄"}
            }.items():
                archive.writestr(filename, json.dumps(values, ensure_ascii=False))
        return path

    def test_reuse_after_model_and_settings_change_and_retranslate_changed_source(self):
        with tempfile.TemporaryDirectory() as folder:
            mods = os.path.join(folder, "mods")
            output = os.path.join(folder, "output")
            os.makedirs(mods)
            jar = self.make_mod(mods, "Stone")
            old_args = self.make_args(mods, output, "plamo-3-translate-8b")
            first = ModTranslator(old_args)
            first.save_plamo_translation(
                "example.jar", "assets/demo/lang/en_us.json", "a", "Stone", "石"
            )
            new_args = self.make_args(
                mods, output, "plamo-3-translate-8b-i1", context="new context"
            )
            with patch("mod_translator.requests.post") as post:
                ModTranslator(new_args).run()
                post.assert_not_called()
            path = os.path.join(output, "assets", "demo", "lang", "ja_jp.json")
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(json.load(stream), {"a": "石", "b": "鉄"})

            self.make_mod(mods, "Granite")
            stat = os.stat(jar)
            os.utime(jar, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
            response = Mock(status_code=200, text="")
            response.json.return_value = {
                "choices": [{"text": "花崗岩", "finish_reason": "stop"}]
            }
            with patch("mod_translator.requests.post", return_value=response) as post:
                ModTranslator(new_args).run()
                self.assertEqual(post.call_count, 1)
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(json.load(stream), {"a": "花崗岩", "b": "鉄"})

    def test_reuse_when_selected_english_locale_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            old = ModTranslator(self.make_args(folder, folder, "plamo-old"))
            old.save_plamo_translation(
                "example.jar", "assets/demo/lang/en_us.json", "a", "Stone", "石"
            )
            new = ModTranslator(self.make_args(folder, folder, "plamo-new"))
            self.assertEqual(
                new.get_plamo_translation(
                    "example.jar", "assets/demo/lang/en_au.json", "a", "Stone"
                ),
                "石"
            )
            self.assertIsNone(
                new.get_plamo_translation(
                    "example.jar", "assets/demo/lang/fr_fr.json", "a", "Stone"
                )
            )
            self.assertIsNone(
                new.get_plamo_translation(
                    "example.jar", "assets/other/lang/en_us.json", "a", "Stone"
                )
            )

    def test_styled_translation_uses_exact_cache_but_not_changed_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            old = ModTranslator(self.make_args(folder, folder, "plamo-old"))
            old.save_plamo_translation(
                "example.jar", "assets/demo/lang/en_us.json", "a", "§aStone", "§a石"
            )
            same = ModTranslator(self.make_args(folder, folder, "plamo-old"))
            self.assertEqual(
                same.get_plamo_translation(
                    "example.jar", "assets/demo/lang/en_us.json", "a", "§aStone"
                ),
                "§a石"
            )
            changed = ModTranslator(self.make_args(folder, folder, "plamo-new"))
            self.assertIsNone(
                changed.get_plamo_translation(
                    "example.jar", "assets/demo/lang/en_us.json", "a", "§aStone"
                )
            )

    def test_repair_cache_from_old_settings_is_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            old = ModTranslator(self.make_args(folder, folder, "plamo-old"))
            old.save_plamo_repair_translation(
                "example.jar", "assets/demo/lang/en_us.json",
                "a", "Count: %s", "個数: %s"
            )
            new = ModTranslator(self.make_args(folder, folder, "plamo-new"))
            self.assertEqual(
                new.get_plamo_translation(
                    "example.jar", "assets/demo/lang/en_us.json", "a", "Count: %s"
                ),
                "個数: %s"
            )
            self.assertIsNone(
                new.get_plamo_translation(
                    "example.jar", "assets/demo/lang/en_us.json", "a", "Count: %d"
                )
            )

    def test_invalid_and_unrelated_cache_entries_are_ignored(self):
        key = json.dumps(
            ["old-settings", "example.jar", "assets/demo/lang/en_us.json",
             "a", "Items: %s"], ensure_ascii=False
        )
        french_key = json.dumps(
            ["old-settings", "example.jar", "assets/demo/lang/fr_fr.json",
             "a", "Pierre"], ensure_ascii=False
        )
        cache = {
            "not-json": "無視",
            key: "項目",
            french_key: "石",
        }
        self.assertEqual(ModTranslator.index_plamo_translations(cache), {})

    def test_cached_translation_replaces_no_official_text(self):
        with tempfile.TemporaryDirectory() as folder:
            mods = os.path.join(folder, "mods")
            output = os.path.join(folder, "output")
            os.makedirs(mods)
            self.make_mod(mods, "Stone")
            translator = ModTranslator(self.make_args(mods, output, "plamo"))
            translator.save_plamo_translation(
                "example.jar", "assets/demo/lang/en_us.json", "a", "Stone", "石"
            )
            translator.save_plamo_translation(
                "example.jar", "assets/demo/lang/en_us.json", "b", "Iron", "AI鉄"
            )
            with patch("mod_translator.requests.post") as post:
                translator.run()
                post.assert_not_called()
            path = os.path.join(output, "assets", "demo", "lang", "ja_jp.json")
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(json.load(stream)["b"], "鉄")


if __name__ == "__main__":
    unittest.main()
