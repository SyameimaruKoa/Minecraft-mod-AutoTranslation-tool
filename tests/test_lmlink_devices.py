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
