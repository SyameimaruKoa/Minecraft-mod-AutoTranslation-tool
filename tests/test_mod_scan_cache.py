import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mod_scan_cache import ModScanCache, TranslationSpeedProfile
from mod_translator import ModTranslator, detect_pack_format, extract_lang_files, extract_japanese_lang_files


def make_mod(folder, filename, language):
    path = Path(folder) / filename
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("assets/demo/lang/en_us.json", json.dumps(language))
    return path


def plamo_args(input_dir, output_dir):
    return SimpleNamespace(
        input=str(input_dir), output=str(output_dir), engine="plamo", key=None,
        model="plamo-3-translate-8b", plamo_models=None, force=False,
        plamo_api_url="http://127.0.0.1:1234/v1/completions",
        plamo_form="plain", plamo_glossary=None, plamo_context="",
        plamo_context_file=None, plamo_history=0, gemma_only=False
    )


class ModScanCacheTests(unittest.TestCase):
    def test_unchanged_mods_reuse_extraction_and_new_mod_is_scanned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mods, output = root / "mods", root / "output"
            mods.mkdir()
            make_mod(mods, "a.jar", {"a": "Stone"})
            scanner = ModScanCache(mods, output)
            with patch("mod_scan_cache.save_atomic_json", wraps=__import__(
                "mod_scan_cache"
            ).save_atomic_json) as save:
                items, stats = scanner.scan(
                    ["a.jar"], extract_lang_files, detect_pack_format
                )
                self.assertEqual(stats, {"reused": 0, "rescanned": 1, "removed": 0})
                self.assertEqual(items[0][1]["assets/demo/lang/en_us.json"], {"a": "Stone"})
                save.assert_called_once()
            scanner = ModScanCache(mods, output)
            with patch("mod_translator.extract_lang_files", side_effect=AssertionError(
                "unchanged archive was opened"
            )):
                items, stats = scanner.scan(
                    ["a.jar"], lambda *args: self.fail("re-parsed unchanged archive"),
                    detect_pack_format
                )
            self.assertEqual(stats["reused"], 1)
            self.assertEqual(items[0][1]["assets/demo/lang/en_us.json"], {"a": "Stone"})
            make_mod(mods, "b.jar", {"b": "Grass"})
            scanner = ModScanCache(mods, output)
            items, stats = scanner.scan(
                ["a.jar", "b.jar"], extract_lang_files, detect_pack_format
            )
            self.assertEqual(stats, {"reused": 1, "rescanned": 1, "removed": 0})
            self.assertEqual([item[0] for item in items], ["a.jar", "b.jar"])

    def test_japanese_scan_cache_is_persisted_without_reopening_unchanged_mod(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mods, output = root / "mods", root / "output"
            mods.mkdir()
            mod = mods / "a.jar"
            with zipfile.ZipFile(mod, "w") as archive:
                archive.writestr(
                    "assets/demo/lang/en_us.json",
                    json.dumps({"a": "Stone"})
                )
                archive.writestr(
                    "assets/demo/lang/ja_jp.json",
                    json.dumps({"a": "石"}, ensure_ascii=False)
                )
            ModScanCache(mods, output).scan(
                ["a.jar"], extract_lang_files, detect_pack_format
            )
            scanner = ModScanCache(mods, output)
            _, changed = scanner.scan(
                ["a.jar"], extract_lang_files, detect_pack_format,
                extract_japanese_lang_files
            )
            self.assertEqual(changed["rescanned"], 1)
            self.assertEqual(
                scanner.japanese_files["a.jar"],
                {"assets/demo/lang/ja_jp.json": {"a": "石"}}
            )
            scanner = ModScanCache(mods, output)
            _, reused = scanner.scan(
                ["a.jar"],
                lambda *args: self.fail("source archive was reopened"),
                lambda *args: self.fail("pack format was rescanned"),
                lambda *args: self.fail("Japanese archive was reopened")
            )
            self.assertEqual(reused, {"reused": 1, "rescanned": 0, "removed": 0})
            self.assertEqual(
                scanner.japanese_files["a.jar"],
                {"assets/demo/lang/ja_jp.json": {"a": "石"}}
            )

    def test_updated_and_removed_mods_invalidate_only_their_cache_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mods, output = root / "mods", root / "output"
            mods.mkdir()
            first = make_mod(mods, "a.jar", {"a": "Stone"})
            make_mod(mods, "b.jar", {"b": "Grass"})
            ModScanCache(mods, output).scan(
                ["a.jar", "b.jar"], extract_lang_files, detect_pack_format
            )
            first = make_mod(mods, "a.jar", {"a": "Granite"})
            st = first.stat()
            os.utime(first, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
            items, stats = ModScanCache(mods, output).scan(
                ["a.jar"], extract_lang_files, detect_pack_format
            )
            self.assertEqual(stats, {"reused": 0, "rescanned": 1, "removed": 1})
            self.assertEqual(
                items[0][1]["assets/demo/lang/en_us.json"], {"a": "Granite"}
            )
            state = json.loads((output / "mod_scan_cache.json").read_text(encoding="utf-8"))
            self.assertEqual(set(state["files"]), {"a.jar"})

    def test_cache_is_scoped_to_input_folder_and_shader_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a, b, out = root / "a", root / "b", root / "output"
            a.mkdir()
            b.mkdir()
            make_mod(a, "same.jar", {"a": "Stone"})
            make_mod(b, "same.jar", {"a": "Dirt"})
            ModScanCache(a, out).scan(["same.jar"], extract_lang_files, detect_pack_format)
            entries, stats = ModScanCache(b, out).scan(
                ["same.jar"], extract_lang_files, detect_pack_format
            )
            self.assertEqual(stats["rescanned"], 1)
            self.assertEqual(
                entries[0][1]["assets/demo/lang/en_us.json"], {"a": "Dirt"}
            )
            _, changed = ModScanCache(b, out, shader_mode=True).scan(
                ["same.jar"], extract_lang_files, detect_pack_format
            )
            self.assertEqual(changed["rescanned"], 1)


class TranslationSpeedTests(unittest.TestCase):
    def test_history_is_persisted_and_scoped_by_model_and_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            speed = TranslationSpeedProfile(folder, ["A", "B"], workers=2)
            self.assertIsNone(speed.estimate(100))
            speed.observe(10, 50)
            self.assertEqual(speed.estimate(100), 500)
            refreshed = TranslationSpeedProfile(folder, ["A", "B"], workers=2)
            self.assertEqual(refreshed.estimate(100), 500)
            refreshed.observe(10, 30)
            self.assertEqual(refreshed.estimate(100), 440)
            separate = TranslationSpeedProfile(folder, ["A", "B"], workers=4)
            self.assertIsNone(separate.estimate(100))

    @patch("mod_translator.requests.post")
    def test_runner_uses_saved_scan_and_new_mod_translates_on_resume(self, post):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mods, output = root / "mods", root / "output"
            mods.mkdir()
            mod_a = make_mod(mods, "a.jar", {"a": "Stone"})
            args = plamo_args(mods, output)
            def reply(url, json, timeout):
                response = Mock(status_code=200, text="")
                response.json.return_value = {
                    "choices": [{"text": "日本語", "finish_reason": "stop"}]
                }
                return response
            post.side_effect = reply
            ModTranslator(args).run()
            self.assertEqual(post.call_count, 1)
            first_state = json.loads(
                (output / "mod_scan_cache.json").read_text(encoding="utf-8")
            )
            with patch("mod_translator.extract_lang_files") as extract:
                ModTranslator(args).run()
                extract.assert_not_called()
            self.assertEqual(post.call_count, 1)
            make_mod(mods, "b.jar", {"b": "Grass"})
            with patch("mod_translator.extract_lang_files", wraps=extract_lang_files) as extract:
                ModTranslator(args).run()
                self.assertEqual(extract.call_count, 1)
            self.assertEqual(post.call_count, 2)
            self.assertIn("b.jar", json.loads(
                (output / "mod_scan_cache.json").read_text(encoding="utf-8")
            )["files"])
            make_mod(mods, "a.jar", {"a": "Granite"})
            st = mod_a.stat()
            os.utime(mod_a, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
            with patch("mod_translator.extract_lang_files", wraps=extract_lang_files) as extract:
                ModTranslator(args).run()
                self.assertEqual(extract.call_count, 1)
            self.assertEqual(post.call_count, 3)
            self.assertEqual(
                ModTranslator(args).get_plamo_translation(
                    "a.jar", "assets/demo/lang/en_us.json", "a", "Granite"
                ),
                "日本語"
            )
            self.assertIn("a.jar", first_state["files"])


if __name__ == "__main__":
    unittest.main()
