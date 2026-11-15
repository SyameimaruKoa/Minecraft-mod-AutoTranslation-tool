import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lmlink_devices import discover_plamo_models, parse_excluded_devices
from mod_translator import ModTranslator


MODELS = [
    {
        "modelKey": "pfnet/plamo-3-translate-8b",
        "identifier": "plamo-local", "deviceIdentifier": None
    },
    {
        "modelKey": "pfnet/plamo-3-translate-8b",
        "identifier": "plamo-prestige", "deviceIdentifier": "device-prestige"
    },
    {
        "modelKey": "pfnet/plamo-3-translate-2b",
        "identifier": "plamo-21kj", "deviceIdentifier": "device-21kj"
    },
    {
        "modelKey": "liquid/lfm2.5-1.2b",
        "identifier": "lfm", "deviceIdentifier": None
    }
]

LINK = {
    "status": "online", "deviceName": "AERO-15X9",
    "peers": [
        {"deviceIdentifier": "device-prestige", "deviceName": "Prestige-13-A13M", "status": "connected"},
        {"deviceIdentifier": "device-21kj", "deviceName": "21KJ", "status": "connected"}
    ]
}


class LMDeviceExclusionTests(unittest.TestCase):
    def test_empty_exclusion_selects_all_loaded_plamo_instances(self):
        with patch("lmlink_devices._lms_json", return_value=MODELS) as cli:
            self.assertEqual(
                discover_plamo_models(),
                ["plamo-local", "plamo-prestige", "plamo-21kj"]
            )
        cli.assert_called_once_with("ps")

    def test_larger_loaded_models_have_higher_priority(self):
        shuffled = [
            {"modelKey": "pfnet/plamo-3-translate-0.8b",
             "identifier": "small", "deviceIdentifier": "device-small"},
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "large", "deviceIdentifier": "device-large"},
            {"modelKey": "pfnet/plamo-3-translate-2b",
             "identifier": "medium", "deviceIdentifier": "device-medium"},
            {"modelKey": "pfnet/plamo-3-translate-31b",
             "identifier": "largest", "deviceIdentifier": "device-largest"},
        ]
        with patch("lmlink_devices._lms_json", return_value=shuffled):
            self.assertEqual(
                discover_plamo_models(),
                ["largest", "large", "medium", "small"]
            )

    def test_same_8b_on_two_pcs_is_distributed(self):
        loaded = [
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "pc-a-8b", "deviceIdentifier": "pc-a"},
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "pc-b-8b", "deviceIdentifier": "pc-b"}
        ]
        with patch("lmlink_devices._lms_json", return_value=loaded):
            self.assertEqual(discover_plamo_models(), ["pc-a-8b", "pc-b-8b"])

    def test_two_plamo_on_same_remote_pc_are_rejected(self):
        loaded = [
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "remote-8b", "deviceIdentifier": "pc-a"},
            {"modelKey": "pfnet/plamo-3-translate-2b",
             "identifier": "remote-2b", "deviceIdentifier": "pc-a"}
        ]
        with patch("lmlink_devices._lms_json", return_value=loaded):
            with self.assertRaisesRegex(RuntimeError, "同一端末"):
                discover_plamo_models()

    def test_two_plamo_on_same_local_pc_are_rejected(self):
        loaded = [
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "local-8b", "deviceIdentifier": None},
            {"modelKey": "pfnet/plamo-3-translate-2b",
             "identifier": "local-2b", "deviceIdentifier": None}
        ]
        with patch("lmlink_devices._lms_json", return_value=loaded):
            with self.assertRaisesRegex(RuntimeError, "1端末につき"):
                discover_plamo_models()

    def test_local_repair_lfm_is_not_second_translation_model(self):
        loaded = [
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "local-8b", "deviceIdentifier": None},
            {"modelKey": "lfm/lfm3-1.7b",
             "identifier": "local-lfm", "deviceIdentifier": None}
        ]
        with patch("lmlink_devices._lms_json", return_value=loaded):
            self.assertEqual(discover_plamo_models(), ["local-8b"])

    def test_explicit_model_filter_overrides_auto_selection(self):
        loaded = [
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "local-8b", "deviceIdentifier": None},
            {"modelKey": "pfnet/plamo-3-translate-2b",
             "identifier": "local-2b", "deviceIdentifier": None}
        ]
        with patch("lmlink_devices._lms_json", return_value=loaded):
            self.assertEqual(
                discover_plamo_models(model_filter="local-8b"), ["local-8b"]
            )

    def test_excluded_pc_with_two_plamo_is_not_selected(self):
        loaded = [
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "local-8b", "deviceIdentifier": None},
            {"modelKey": "pfnet/plamo-3-translate-8b",
             "identifier": "remote-8b", "deviceIdentifier": "pc-a"},
            {"modelKey": "pfnet/plamo-3-translate-2b",
             "identifier": "remote-2b", "deviceIdentifier": "pc-a"}
        ]
        link = {
            "status": "online", "deviceName": "local-machine",
            "peers": [{"deviceIdentifier": "pc-a", "deviceName": "Remote-PC"}]
        }
        with patch("lmlink_devices._lms_json", side_effect=[loaded, link]):
            self.assertEqual(discover_plamo_models("Remote-PC"), ["local-8b"])

    def test_exclude_by_device_id_or_name(self):
        with patch("lmlink_devices._lms_json", side_effect=[MODELS, LINK]):
            self.assertEqual(
                discover_plamo_models("device-prestige"),
                ["plamo-local", "plamo-21kj"]
            )
        with patch("lmlink_devices._lms_json", side_effect=[MODELS, LINK]):
            self.assertEqual(
                discover_plamo_models("Prestige-13-A13M,21KJ"),
                ["plamo-local"]
            )

    def test_exclude_local_device_by_device_name_or_local_alias(self):
        for excluded in ["AERO-15X9", "LOCAL"]:
            with patch("lmlink_devices._lms_json", side_effect=[MODELS, LINK]):
                self.assertEqual(
                    discover_plamo_models(excluded),
                    ["plamo-prestige", "plamo-21kj"]
                )

    def test_different_model_filter(self):
        with patch("lmlink_devices._lms_json", return_value=MODELS):
            self.assertEqual(
                discover_plamo_models(model_filter="pfnet/plamo-3-translate-2b"),
                ["plamo-21kj"]
            )

    def test_unknown_device_is_not_ignored(self):
        with patch("lmlink_devices._lms_json", side_effect=[MODELS, LINK]):
            with self.assertRaisesRegex(ValueError, "見つかりません"):
                discover_plamo_models("nonexistent")

    def test_all_devices_excluded_raises_before_inference(self):
        with patch("lmlink_devices._lms_json", side_effect=[MODELS, LINK]):
            with self.assertRaisesRegex(RuntimeError, "使用可能"):
                discover_plamo_models("local,21KJ,Prestige-13-A13M")

    def test_duplicate_model_id_across_devices_is_rejected_even_when_excluded(self):
        duplicate = [
            dict(MODELS[0]),
            dict(MODELS[1], identifier="plamo-local")
        ]
        with patch("lmlink_devices._lms_json", side_effect=[duplicate, LINK]):
            with self.assertRaisesRegex(RuntimeError, "除外した端末"):
                discover_plamo_models("Prestige-13-A13M")
        with patch("lmlink_devices._lms_json", return_value=duplicate):
            with self.assertRaisesRegex(RuntimeError, "複数"):
                discover_plamo_models()

    def test_duplicate_or_empty_exclusion_ids_are_rejected(self):
        for value in ["21KJ,21kj", "local,", ",local", "local,,21KJ"]:
            with self.assertRaises(ValueError):
                parse_excluded_devices(value)

    def test_windows_cli_finds_installation_without_path(self):
        from pathlib import Path
        from lmlink_devices import find_lms_executable
        for location in (".lmstudio", ".cache/lm-studio"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as folder:
                cli = Path(folder) / location / "bin" / "lms.exe"
                cli.parent.mkdir(parents=True)
                cli.touch()
                with patch("lmlink_devices.IS_WINDOWS", True), \
                     patch("lmlink_devices.Path.home", return_value=Path(folder)), \
                     patch("lmlink_devices.shutil.which", return_value=None):
                    self.assertEqual(find_lms_executable(), str(cli))

    def test_windows_cli_respects_custom_home_pointer(self):
        from pathlib import Path
        from lmlink_devices import find_lms_executable
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / "home"
            custom = Path(folder) / "custom"
            home.mkdir()
            cli = custom / "bin" / "lms.exe"
            cli.parent.mkdir(parents=True)
            cli.touch()
            (home / ".lmstudio-home-pointer").write_text(str(custom), encoding="utf-8")
            with patch("lmlink_devices.IS_WINDOWS", True), \
                 patch("lmlink_devices.Path.home", return_value=home), \
                 patch("lmlink_devices.shutil.which", return_value=None):
                self.assertEqual(find_lms_executable(), str(cli))

    def test_windows_cli_uses_path_when_available(self):
        from lmlink_devices import find_lms_executable
        with patch("lmlink_devices.IS_WINDOWS", True), \
             patch("lmlink_devices.shutil.which", return_value=r"C:\LM Studio\lms.exe"):
            self.assertEqual(find_lms_executable(), r"C:\LM Studio\lms.exe")

    def test_windows_cli_is_used_for_lms_ps_json(self):
        from lmlink_devices import _lms_json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            cli = Path(folder) / ".lmstudio" / "bin" / "lms.exe"
            cli.parent.mkdir(parents=True)
            cli.touch()
            with patch("lmlink_devices.IS_WINDOWS", True), \
                 patch("lmlink_devices.Path.home", return_value=Path(folder)), \
                 patch("lmlink_devices.shutil.which", return_value=None), \
                 patch("lmlink_devices.subprocess.run", return_value=SimpleNamespace(
                     returncode=0, stdout='[{"modelKey":"plamo-3-translate-8b"}]', stderr=""
                 )) as execute:
                self.assertEqual(_lms_json("ps")[0]["modelKey"], "plamo-3-translate-8b")
                self.assertEqual(execute.call_args.args[0], [str(cli), "ps", "--json"])

    def test_windows_cli_missing_has_actionable_error(self):
        from pathlib import Path
        from lmlink_devices import _lms_json
        with tempfile.TemporaryDirectory() as folder:
            with patch("lmlink_devices.IS_WINDOWS", True), \
                 patch("lmlink_devices.Path.home", return_value=Path(folder)), \
                 patch("lmlink_devices.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, r"lms.exe"):
                    _lms_json("ps")

    def test_missing_lms_cli_is_reported(self):
        with patch("lmlink_devices.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(RuntimeError, "lms ps"):
                discover_plamo_models()

    @patch("mod_translator.require_loaded_lm_studio_model", side_effect=lambda model, *args: model)
    @patch("mod_translator.discover_plamo_models", return_value=["plamo-local", "plamo-prestige"])
    def test_translator_auto_discovers_all_and_reuses_model_cache(self, discover, require):
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(
                input=folder, output=folder, engine="plamo", key=None,
                model=None, exclude_devices=None, plamo_models=None,
                plamo_api_url="http://127.0.0.1:1234/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=3,
                gemma_only=False, force=False, repair_model=None,
                repair_api_url="http://127.0.0.1:1234/v1/chat/completions",
                model_load_policy="wait"
            )
            translator = ModTranslator(args)
            discover.assert_called_once_with([], model_filter=None)
            self.assertEqual(translator.plamo_models, ["plamo-local", "plamo-prestige"])
            translator.save_plamo_translation(
                "mod.jar", "assets/test/lang/en_us.json", "a", "Stone", "石",
                model_name="plamo-prestige"
            )
            other = ModTranslator(args)
            self.assertEqual(
                other.get_plamo_translation(
                    "mod.jar", "assets/test/lang/en_us.json", "a", "Stone"
                ), "石"
            )


if __name__ == "__main__":
    unittest.main()
