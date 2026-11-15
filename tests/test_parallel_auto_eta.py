import json
import tempfile
import threading
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mod_scan_cache import TranslationETA, TranslationSpeedProfile
from mod_translator import ModTranslator, detect_plamo_parallel_limit


def api_inventory(parallel):
    return {"models": [{
        "type": "llm", "key": "pfnet/plamo-3-translate-8b",
        "loaded_instances": [{
            "id": "plamo-3-translate-8b",
            "config": {"parallel": parallel}
        }]
    }]}


class ParallelAutoTests(unittest.TestCase):
    @patch("mod_translator.requests.get")
    def test_reads_official_loaded_parallel_from_local_api(self, get):
        response = Mock(status_code=200)
        response.json.return_value = api_inventory(4)
        get.return_value = response
        self.assertEqual(
            detect_plamo_parallel_limit(
                "http://127.0.0.1:1234/v1/completions",
                ["plamo-3-translate-8b"]
            ), 4
        )
        self.assertEqual(
            get.call_args.args[0],
            "http://127.0.0.1:1234/api/v1/models"
        )

    @patch("mod_translator.requests.get")
    def test_ambiguous_same_id_uses_safe_minimum(self, get):
        inventory = api_inventory(4)
        inventory["models"].append({
            "type": "llm", "key": "pfnet/plamo-3-translate-8b",
            "loaded_instances": [{
                "id": "plamo-3-translate-8b",
                "config": {"parallel": 2}
            }]
        })
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = inventory
        self.assertEqual(
            detect_plamo_parallel_limit(
                "http://127.0.0.1:1234/v1/completions",
                ["plamo-3-translate-8b"]
            ), 2
        )

    @patch("mod_translator.requests.get", side_effect=RuntimeError("offline"))
    def test_unexpected_failure_is_not_silently_hidden(self, get):
        with self.assertRaisesRegex(RuntimeError, "offline"):
            detect_plamo_parallel_limit(
                "http://127.0.0.1:1234/v1/completions",
                ["plamo-3-translate-8b"]
            )

    @patch("mod_translator.requests.get")
    def test_missing_parallel_configuration_falls_back_to_two(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {"models": []}
        get.return_value = response
        self.assertEqual(
            detect_plamo_parallel_limit(
                "http://127.0.0.1:1234/v1/completions",
                ["plamo-3-translate-8b"]
            ), 2
        )

    @patch("mod_translator.requests.post")
    @patch("mod_translator.requests.get")
    def test_auto_mode_sends_four_requests_at_once(self, get, post):
        response = Mock(status_code=200)
        response.json.return_value = api_inventory(4)
        get.return_value = response
        reached = []
        lock = threading.Lock()
        barrier = threading.Barrier(4, timeout=5)

        def reply(url, json, timeout):
            with lock:
                reached.append(json["model"])
            barrier.wait()
            value = Mock(status_code=200, text="")
            value.json.return_value = {
                "choices": [{"text": "日本語", "finish_reason": "stop"}]
            }
            return value

        post.side_effect = reply
        with tempfile.TemporaryDirectory() as folder:
            mods = Path(folder) / "mods"
            output = Path(folder) / "output"
            mods.mkdir()
            with zipfile.ZipFile(mods / "test.jar", "w") as archive:
                archive.writestr(
                    "assets/example/lang/en_us.json",
                    json.dumps({
                        "item.a": "Stone", "item.b": "Dirt",
                        "item.c": "Grass", "item.d": "Wood"
                    })
                )
            args = SimpleNamespace(
                input=str(mods), output=str(output), engine="plamo",
                key=None, model="plamo-3-translate-8b",
                plamo_models=None, force=False, workers="auto",
                plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=0,
                gemma_only=False, repair_model=None
            )
            translator = ModTranslator(args)
            self.assertEqual(translator.workers, 4)
            translator.run()
            self.assertEqual(post.call_count, 4)
            self.assertEqual(reached, ["plamo-3-translate-8b"] * 4)


class StableETATests(unittest.TestCase):
    def test_initial_eta_and_local_completion_datetime(self):
        now = [0.0]
        japan = timezone(timedelta(hours=9))
        clock = lambda: now[0]
        wall = lambda: datetime(2026, 11, 16, 0, 0, tzinfo=japan)
        estimator = TranslationETA(
            100, prior_seconds_per_item=2,
            clock=clock, wall_clock=wall
        )
        self.assertEqual(estimator.estimate(0), (200, "2026-11-16 00:03"))
        now[0] = 100
        first = estimator.estimate(25)
        self.assertGreater(first[0], 150)
        self.assertLess(first[0], 250)
        self.assertEqual(
            estimator.estimate(25), first
        )
        now[0] = 200
        self.assertEqual(estimator.estimate(100), (0, "2026-11-16 00:00"))

    def test_eta_uses_cumulative_progress_not_mod_restart(self):
        now = [0.0]
        clock = lambda: now[0]
        estimator = TranslationETA(
            100, clock=clock,
            wall_clock=lambda: datetime(2026, 11, 16, 10, 0)
        )
        now[0] = 20
        a = estimator.estimate(10)[0]
        now[0] = 60
        b = estimator.estimate(30)[0]
        self.assertEqual(a, 180)
        self.assertEqual(b, 140)

    def test_speed_profile_updates_from_cumulative_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            speed = TranslationSpeedProfile(folder, ["plamo"], 4)
            speed.observe_cumulative(10, 20)
            speed.observe_cumulative(30, 60)
            speed.observe_cumulative(30, 61)
            self.assertEqual(speed.estimate(100), 200)

    def test_power_shell_launcher_preserves_bom_and_auto_default(self):
        content = (
            Path(__file__).resolve().parents[1] / "start.ps1"
        ).read_text(encoding="utf-8-sig")
        data = (
            Path(__file__).resolve().parents[1] / "start.ps1"
        ).read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn('[string]$Workers = "auto"', content)
        self.assertIn('$effectiveWorkers', content)


if __name__ == "__main__":
    unittest.main()
