import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch
from urllib.error import URLError

from lmlink_devices import find_lms_executable
from plamo_identifier import automatic_identifier, ensure_link_enabled, load_configuration, main


MODEL_KEY = "pfnet/plamo-3-translate-8b-GGUF/plamo-3-translate-8b-Q4_K_M.gguf"
LOCAL = {"modelKey": MODEL_KEY, "identifier": "plamo-3-translate-8b"}
REMOTE = dict(LOCAL, deviceIdentifier="some-remote-pc")


class CrossPlatformClusterTests(unittest.TestCase):
    @patch("plamo_identifier.uuid.getnode", return_value=0x001122334455)
    @patch("plamo_identifier.platform.node", return_value="Other Windows PC")
    def test_auto_id_is_stable_and_contains_model_size_and_device(self, node, mac):
        identifier = automatic_identifier(MODEL_KEY)
        self.assertEqual(
            identifier, automatic_identifier(MODEL_KEY)
        )
        self.assertTrue(identifier.startswith("plamo-3-translate-8b-other-windows-pc-"))
        self.assertRegex(identifier, r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

    @patch("plamo_identifier.uuid.getnode", return_value=0x001122334455)
    @patch("plamo_identifier.platform.node", return_value="linux-a")
    def test_ids_differ_across_different_machines(self, node, mac):
        a = automatic_identifier(MODEL_KEY)
        with patch("plamo_identifier.platform.node", return_value="linux-b"):
            b = automatic_identifier(MODEL_KEY)
        self.assertNotEqual(a, b)

    @patch("plamo_identifier.ensure_link_enabled")
    @patch("plamo_identifier.rename_local_model")
    @patch("plamo_identifier.loaded_plamo_models")
    def test_join_loaded_windows_or_linux_model(self, loaded, rename, link):
        loaded.return_value = [LOCAL, REMOTE]
        with patch("plamo_identifier.automatic_identifier", return_value="plamo-3-translate-8b-node-a"):
            with patch.object(sys, "argv", ["plamo_identifier.py", "--join", "--yes"]):
                main()
        rename.assert_called_once_with(
            "plamo-3-translate-8b", "plamo-3-translate-8b-node-a"
        )

    @patch("plamo_identifier.ensure_link_enabled")
    @patch("plamo_identifier.rename_local_model")
    @patch("plamo_identifier.loaded_plamo_models")
    def test_join_already_registered_is_idempotent(self, loaded, rename, link):
        local = dict(LOCAL, identifier="plamo-3-translate-8b-node-a")
        loaded.return_value = [local]
        with patch("plamo_identifier.automatic_identifier", return_value=local["identifier"]):
            with patch.object(sys, "argv", ["plamo_identifier.py", "--join", "--yes"]):
                main()
        rename.assert_not_called()

    @patch("plamo_identifier.loaded_plamo_models")
    @patch("plamo_identifier.lms")
    def test_join_can_load_selected_model_on_other_pc_without_http_exposure(self, lms, loaded):
        new_id = "plamo-3-translate-8b-node-b"
        loaded.side_effect = [[], [dict(LOCAL, identifier=new_id)]]
        lms.side_effect = lambda *args, **kwargs: (
            {"status": "online", "issues": []} if args == ("link", "status") else ""
        )
        with patch("plamo_identifier.automatic_identifier", return_value=new_id):
            with patch.object(sys, "argv", [
                "plamo_identifier.py", "--join", "--model-key", MODEL_KEY, "--yes"
            ]):
                main()
        self.assertEqual(lms.call_args_list, [
            call("link", "status", json_output=True, required=False),
            call("link", "disable"),
            call("load", MODEL_KEY, "--identifier", new_id, "-y"),
            call("link", "enable"),
            call("link", "status", json_output=True, required=False)
        ])

    @patch("plamo_identifier.loaded_plamo_models", return_value=[])
    def test_missing_model_without_key_is_explicit_error(self, loaded):
        with patch.object(sys, "argv", ["plamo_identifier.py", "--join", "--yes"]):
            with self.assertRaises(SystemExit) as failure:
                main()
        self.assertNotEqual(failure.exception.code, 0)

    @patch("plamo_identifier.loaded_plamo_models")
    @patch("plamo_identifier.urlopen", side_effect=URLError("not running"))
    def test_config_uses_official_lms_if_local_http_api_is_not_started(self, urlopen, loaded):
        loaded.return_value = [dict(LOCAL, parallel=4, contextLength=8192)]
        self.assertEqual(
            load_configuration(LOCAL["identifier"]),
            (MODEL_KEY, {"parallel": 4, "context_length": 8192})
        )

    @patch("plamo_identifier.lms")
    def test_join_enables_disabled_lm_link(self, lms):
        lms.return_value = {"status": "offline", "issues": ["deviceDisabled"]}
        ensure_link_enabled()
        lms.assert_any_call("link", "enable")

    @patch("plamo_identifier.lms")
    def test_join_reports_missing_lm_link_login(self, lms):
        lms.return_value = {"status": "offline", "issues": ["notLoggedIn"]}
        with self.assertRaisesRegex(RuntimeError, "lms login"):
            ensure_link_enabled()

    @patch("lmlink_devices.IS_WINDOWS", False)
    @patch("lmlink_devices.shutil.which", return_value=None)
    def test_linux_lms_resolves_from_installed_home(self, which):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".lmstudio" / "bin" / "lms"
            path.parent.mkdir(parents=True)
            path.touch()
            with patch("lmlink_devices.Path.home", return_value=Path(directory)):
                self.assertEqual(find_lms_executable(), str(path))


if __name__ == "__main__":
    unittest.main()
