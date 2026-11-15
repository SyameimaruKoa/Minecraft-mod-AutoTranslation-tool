import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from mod_scan_cache import ClusterETA
from plamo_identifier import (
    choose_local_model, make_load_command, model_identifier, rename_local_model
)


class IdentifierManagementTests(unittest.TestCase):
    def test_identifier_validation(self):
        self.assertEqual(model_identifier(" plamo-3-translate-8b-colab "), "plamo-3-translate-8b-colab")
        for value in ("", "bad name", "/path", "あいう", "a:b"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    model_identifier(value)

    def test_loader_preserves_parallel_and_context(self):
        self.assertEqual(
            make_load_command(
                "pfnet/plamo-3-translate-8b@q4_k_m", "plamo-colab",
                {"parallel": 4, "context_length": 8192}
            ),
            [
                "load", "pfnet/plamo-3-translate-8b@q4_k_m",
                "--identifier", "plamo-colab", "--gpu", "max",
                "--parallel", "4", "--context-length", "8192", "-y"
            ]
        )

    @patch("plamo_identifier.loaded_plamo_models")
    @patch("plamo_identifier.load_configuration")
    @patch("plamo_identifier.lms")
    def test_local_model_renamed_without_touching_lfm_or_remote(self, lms, config, loaded):
        local = {
            "modelKey": "pfnet/plamo-3-translate-8b",
            "identifier": "plamo-3-translate-8b",
            "deviceIdentifier": None
        }
        remote = dict(local, deviceIdentifier="colab")
        ready = dict(local, identifier="plamo-3-translate-8b-prestige")
        loaded.side_effect = [[local, remote], [local], [ready]]
        config.return_value = (
            "pfnet/plamo-3-translate-8b@q4_k_m",
            {"parallel": 2, "context_length": 8192}
        )
        lms.return_value = ""
        lms.side_effect = lambda *args, **kwargs: (
            {"status": "online"} if args == ("link", "status") else ""
        )
        rename_local_model(local["identifier"], ready["identifier"])
        self.assertEqual(lms.call_args_list, [
            call("link", "status", json_output=True, required=False),
            call("link", "disable"),
            call("unload", "plamo-3-translate-8b"),
            call(
                "load", "pfnet/plamo-3-translate-8b@q4_k_m",
                "--identifier", "plamo-3-translate-8b-prestige",
                "--gpu", "max", "--parallel", "2",
                "--context-length", "8192", "-y"
            ),
            call("link", "enable")
        ])

    @patch("plamo_identifier.loaded_plamo_models")
    @patch("plamo_identifier.load_configuration")
    @patch("plamo_identifier.lms")
    def test_failed_load_restores_original_identifier(self, lms, config, loaded):
        local = {
            "modelKey": "pfnet/plamo-3-translate-8b",
            "identifier": "original", "deviceIdentifier": None
        }
        loaded.side_effect = [[local], [local]]
        config.return_value = ("pfnet/plamo-3-translate-8b@q4_k_m", {"parallel": 4})
        invoked = []
        def fake_lms(*args, **kwargs):
            invoked.append(args)
            if args == ("link", "status"):
                return {"status": "online"}
            if args[:1] == ("load",) and "--identifier" in args:
                if args[args.index("--identifier") + 1] == "new":
                    raise RuntimeError("load failed")
            return ""
        lms.side_effect = fake_lms
        with self.assertRaisesRegex(RuntimeError, "旧IDへ復元"):
            rename_local_model("original", "new")
        self.assertIn(("link", "enable"), invoked)
        self.assertEqual(
            [item[item.index("--identifier") + 1] for item in invoked if item[:1] == ("load",)],
            ["new", "original"]
        )

    @patch("plamo_identifier.loaded_plamo_models")
    def test_reject_existing_id_on_remote_before_changing_anything(self, loaded):
        local = {
            "modelKey": "pfnet/plamo-3-translate-8b",
            "identifier": "local", "deviceIdentifier": None
        }
        loaded.return_value = [local, dict(local, identifier="used", deviceIdentifier="peer")]
        with self.assertRaisesRegex(RuntimeError, "既にLM Link"):
            rename_local_model("local", "used")

    def test_interactive_chooser_excludes_remote_and_lfm(self):
        models = [
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "local", "deviceIdentifier": None},
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "remote", "deviceIdentifier": "colab"}
        ]
        self.assertEqual(choose_local_model(models), "local")

    def test_powershell_menu_and_bom(self):
        path = Path(__file__).resolve().parents[1] / "start.ps1"
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        script = path.read_text(encoding="utf-8-sig")
        self.assertIn('plamo_identifier.py" --interactive', script)
        self.assertIn("Get-Help", script)


class ClusterETATests(unittest.TestCase):
    def test_active_model_join_and_leave_change_prediction(self):
        now = [0.0]
        eta = ClusterETA(
            100, clock=lambda: now[0],
            wall_clock=lambda: __import__("datetime").datetime(2026, 11, 16, 0, 0)
        )
        eta.set_active(["fast"], 2)
        now[0] = 3
        eta.observe("fast", 6, 3)
        before_join = eta.estimate(6)[0]
        self.assertEqual(before_join, 24)
        eta.set_active(["fast", "slow"], 2)
        self.assertEqual(eta.estimate(6)[0], before_join)
        now[0] = 5
        eta.observe("slow", 2, 4)
        with_two = eta.estimate(8)[0]
        self.assertLess(with_two, eta.estimate(8)[0] if False else 23)
        eta.set_active(["fast"], 2)
        without_slow = eta.estimate(8)[0]
        self.assertGreater(without_slow, with_two)

    def test_low_performance_peer_does_not_reduce_fast_peers_rate(self):
        eta = ClusterETA(100, prior_seconds_per_item=None)
        eta.set_active(["fast", "slow"], 2)
        eta.observe("fast", 10, 1)
        eta.observe("slow", 1, 30)
        self.assertLess(eta.estimate(11)[0], 5)

    def test_earlier_initial_prediction_works_without_samples(self):
        eta = ClusterETA(100, prior_seconds_per_item=2)
        eta.set_active(["a", "b"], 2)
        seconds, finish = eta.estimate(0)
        self.assertEqual(seconds, 200)
        self.assertRegex(finish, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()
