import ast
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


NOTEBOOK = Path(__file__).resolve().parents[1] / "run_colab_server.ipynb"


class ColabNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.code_cells = [
            "".join(cell["source"])
            for cell in cls.notebook["cells"]
            if cell["cell_type"] == "code"
        ]

    def test_code_cells_are_valid_python(self):
        for index, code in enumerate(self.code_cells):
            with self.subTest(cell=index):
                ast.parse(code)

    def test_download_uses_official_exact_gguf_and_resumes(self):
        code = self.code_cells[-1]
        self.assertIn('f"plamo-3-translate-{plamo_size}-{quantization}.gguf"', code)
        self.assertIn("https://huggingface.co/pfnet/", code)
        self.assertIn('"--continue-at", "-"', code)
        self.assertIn("os.replace(partial_path, model_path)", code)
        self.assertIn('"lms", "load"', code)
        self.assertNotIn('"lms", "get"', code)
        self.assertNotIn('subprocess.DEVNULL)', code)

    def test_auth_state_is_copied_directly_without_extra_passwords(self):
        code = self.code_cells[2]
        self.assertIn('AUTH_DIRS = ("credentials",)', code)
        self.assertIn('".internal/local-identity.json"', code)
        self.assertIn('".internal/user-profile.json"', code)
        self.assertIn('LM_CACHE_HOME = Path.home() / ".cache" / "lm-studio"', code)
        self.assertIn('shutil.copy2(original, target)', code)
        self.assertIn('auth_restored = restore_login()', code)
        self.assertNotIn("AESGCM", code)
        self.assertNotIn("getpass", code)
        self.assertNotIn("LM_LINK_VAULT_PASSWORD", code)

    def build_auth_functions(self, live, cache, saved):
        code = self.code_cells[2]
        functions = [
            node for node in ast.parse(code).body
            if isinstance(node, ast.FunctionDef)
            and node.name in (
                "auth_roots", "copy_login_files", "restore_login", "backup_login"
            )
        ]
        namespace = {
            "os": os, "shutil": shutil,
            "AUTH_DIRS": ("credentials",),
            "IDENTITY_FILES": (
                ".internal/local-identity.json", ".internal/user-profile.json"
            ),
            "LM_HOME": live, "LM_CACHE_HOME": cache,
            "DRIVE_AUTH_DIR": saved, "USE_GOOGLE_DRIVE": True
        }
        compiled = ast.Module(body=functions, type_ignores=[])
        exec(compile(compiled, "<notebook>", "exec"), namespace)
        return namespace

    def test_auth_state_backup_and_restore_from_both_locations(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            live = root / "runtime" / ".lmstudio"
            cache = root / "runtime" / ".cache" / "lm-studio"
            saved = root / "drive" / ".colab-secret" / "lmstudio"
            (live / "credentials").mkdir(parents=True)
            (cache / "credentials").mkdir(parents=True)
            (cache / ".internal").mkdir(parents=True)
            (live / "credentials" / "lmstudio-hub.json").write_bytes(b"dummy-old")
            (cache / "credentials" / "lmstudio-hub.json").write_bytes(b"dummy-new")
            (cache / ".internal" / "local-identity.json").write_bytes(b"dummy-identity")
            namespace = self.build_auth_functions(live, cache, saved)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(namespace["backup_login"](), 3)
            self.assertEqual(
                (saved / "lmstudio" / "credentials" / "lmstudio-hub.json").read_bytes(),
                b"dummy-old"
            )
            self.assertEqual(
                (saved / "lm-studio-cache" / "credentials" / "lmstudio-hub.json").read_bytes(),
                b"dummy-new"
            )
            shutil.rmtree(root / "runtime")
            with redirect_stdout(io.StringIO()):
                self.assertTrue(namespace["restore_login"]())
            self.assertEqual(
                (cache / "credentials" / "lmstudio-hub.json").read_bytes(),
                b"dummy-new"
            )
            self.assertEqual(
                (cache / ".internal" / "local-identity.json").read_bytes(),
                b"dummy-identity"
            )
            namespace["USE_GOOGLE_DRIVE"] = False
            self.assertFalse(namespace["restore_login"]())
            self.assertEqual(namespace["backup_login"](), 0)

    def test_missing_backup_is_warning_and_does_not_expose_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            namespace = self.build_auth_functions(
                root / ".lmstudio", root / ".cache" / "lm-studio",
                root / "drive" / ".colab-secret" / "lmstudio"
            )
            capture = io.StringIO()
            with redirect_stdout(capture):
                self.assertEqual(namespace["backup_login"](), 0)
            self.assertIn("[WARN]", capture.getvalue())
            self.assertIn("処理は続行", capture.getvalue())
            self.assertFalse((root / "drive").exists())

    def test_restore_supports_old_flat_drive_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            live = root / ".lmstudio"
            cache = root / ".cache" / "lm-studio"
            saved = root / "drive" / ".colab-secret" / "lmstudio"
            (saved / "credentials").mkdir(parents=True)
            (saved / "credentials" / "lmstudio-hub.json").write_bytes(b"old-state")
            namespace = self.build_auth_functions(live, cache, saved)
            with redirect_stdout(io.StringIO()):
                self.assertTrue(namespace["restore_login"]())
            self.assertEqual(
                (live / "credentials" / "lmstudio-hub.json").read_bytes(),
                b"old-state"
            )

    def test_login_restore_order_and_no_committed_outputs(self):
        configuration, startup, restore, login, model = self.code_cells
        self.assertIn('USE_GOOGLE_DRIVE = True', configuration)
        self.assertIn('DRIVE_FOLDER_NAME = ".colab-secret"', configuration)
        self.assertIn('lms", "bootstrap"', startup)
        self.assertIn('auth_restored = restore_login()', restore)
        self.assertIn('lms", "daemon", "up"', login)
        self.assertIn('lms", "whoami"', login)
        self.assertIn('lms", "login"', login)
        self.assertIn('lms", "link", "enable"', login)
        self.assertLess(login.index('"lms", "link", "enable"'), login.index("backup_login()"))
        for cell in self.notebook["cells"]:
            if cell["cell_type"] == "code":
                self.assertEqual(cell["outputs"], [])
                self.assertIsNone(cell["execution_count"])

    def test_drive_destination_matches_dbv4_notebook(self):
        configuration = self.code_cells[0]
        restore = self.code_cells[2]
        self.assertIn('DRIVE_FOLDER_NAME = ".colab-secret"', configuration)
        self.assertIn('"/content/drive/MyDrive"', restore)
        self.assertIn('CONFIG_DRIVE_FOLDER / "lmstudio"', restore)
        self.assertIn('if USE_GOOGLE_DRIVE:', restore)
        self.assertIn('if not USE_GOOGLE_DRIVE:', restore)
        self.assertIn('drive.mount("/content/drive")', restore)

    def test_official_gguf_formats_match_pfnet_published_files(self):
        code = self.code_cells[-1]
        tree = ast.parse(code)
        formats = next(
            node.value for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "OFFICIAL_GGUF_FORMATS"
                    for target in node.targets)
        )
        available = ast.literal_eval(formats)
        self.assertEqual(set(available), {"0.8b", "2b", "8b", "31b"})
        for size in ("0.8b", "2b"):
            self.assertEqual(
                set(available[size]), {"Q4_K_M", "Q4_0", "Q3_K_M", "Q2_K"}
            )
        for size in ("8b", "31b"):
            self.assertEqual(
                set(available[size]), {"Q4_K_M", "Q3_K_M", "Q2_K"}
            )
        self.assertNotIn("Q4_0", available["8b"])
        self.assertNotIn("Q4_0", available["31b"])

    def test_only_valid_quantization_combination(self):
        source = self.code_cells[-1]
        self.assertIn('plamo_size = "8b"', source)
        self.assertIn('if quantization not in OFFICIAL_GGUF_FORMATS[plamo_size]:', source)
        self.assertIn('model_id = f"plamo-3-translate-{plamo_size}-colab"', source)


if __name__ == "__main__":
    unittest.main()
