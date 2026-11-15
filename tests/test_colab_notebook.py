import ast
import json
import os
import shutil
import tempfile
import unittest
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

    @classmethod
    def find_code(cls, marker):
        return next(code for code in cls.code_cells if marker in code)

    def test_download_uses_official_exact_gguf_and_resumes(self):
        code = self.code_cells[-1]
        self.assertIn('f"plamo-3-translate-{plamo_size}-{quantization}.gguf"', code)
        self.assertIn("https://huggingface.co/pfnet/", code)
        self.assertIn('"Range": f"bytes={offset}-"', code)
        self.assertIn("response.status_code == 206", code)
        self.assertIn("current != total", code)
        self.assertIn("os.replace(partial, complete)", code)
        self.assertIn("download_with_progress(url, partial_path, model_path)", code)
        self.assertIn('"lms", "load"', code)
        self.assertNotIn('"lms", "get"', code)
        self.assertNotIn('subprocess.DEVNULL)', code)

    def test_auth_state_is_copied_directly_without_extra_passwords(self):
        code = self.find_code("def backup_login():")
        self.assertIn('AUTH_DIRS = ("credentials", "hub")', code)
        self.assertIn('shutil.copy2(original, target)', code)
        self.assertIn('auth_restored = restore_login()', code)
        self.assertNotIn("AESGCM", code)
        self.assertNotIn("getpass", code)
        self.assertNotIn("LM_LINK_VAULT_PASSWORD", code)
        copy_function = code.split("def copy_login_files(source, destination):", 1)[1].split("def restore_login():", 1)[0]
        self.assertNotIn('".internal"', copy_function)

    def test_auth_state_backup_and_restore_without_reauthentication(self):
        code = self.find_code("def backup_login():")
        defs = [
            node for node in ast.parse(code).body
            if isinstance(node, ast.FunctionDef)
            and node.name in ("copy_login_files", "restore_login", "backup_login")
        ]
        namespace = {"os": os, "shutil": shutil, "AUTH_DIRS": ("credentials", "hub")}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            live = root / "runtime"
            saved = root / "drive" / ".colab-secret" / "lmstudio"
            (live / "credentials").mkdir(parents=True)
            (live / "hub").mkdir()
            (live / "credentials" / "lmstudio-hub.json").write_bytes(b"dummy-credentials")
            (live / "hub" / "session.json").write_bytes(b"dummy-session")
            namespace.update(
                LM_HOME=live, DRIVE_AUTH_DIR=saved, USE_GOOGLE_DRIVE=True
            )
            exec(compile(ast.Module(body=defs, type_ignores=[]), "<notebook>", "exec"), namespace)
            namespace["backup_login"]()
            self.assertEqual(
                (saved / "credentials" / "lmstudio-hub.json").read_bytes(),
                b"dummy-credentials"
            )
            shutil.rmtree(live)
            self.assertTrue(namespace["restore_login"]())
            self.assertEqual(
                (live / "credentials" / "lmstudio-hub.json").read_bytes(),
                b"dummy-credentials"
            )
            self.assertEqual(
                (live / "hub" / "session.json").read_bytes(), b"dummy-session"
            )
            namespace["USE_GOOGLE_DRIVE"] = False
            self.assertFalse(namespace["restore_login"]())
            namespace["backup_login"]()

    def test_login_restore_order_and_no_committed_outputs(self):
        configuration = self.find_code('USE_GOOGLE_DRIVE = True')
        startup = self.find_code('run_console(["lms", "bootstrap"])')
        restore = self.find_code("def backup_login():")
        login = self.find_code('run_console(["lms", "daemon", "up"])')
        model = self.find_code("OFFICIAL_GGUF_FORMATS =")
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
        restore = self.find_code("def backup_login():")
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

    def test_model_lookup_uses_local_rest_without_broken_cli_listing(self):
        code = self.code_cells[-1]
        self.assertIn('run_console(["lms", "server", "start", "--port", "1234"])', code)
        self.assertIn('unload_local_models_with_retry()', code)
        self.assertIn('run_console(["lms", "link", "enable"])', code)
        self.assertIn('http://127.0.0.1:1234/api/v1/models', code)
        self.assertIn('"--parallel", str(PARALLEL_REQUESTS)', code)
        self.assertNotIn('read_lms_json', code)
        self.assertNotIn('"lms", "ls"', code)
        self.assertNotIn('"lms", "ps"', code)

    def test_colab_unload_recovers_from_connector_closed(self):
        from types import SimpleNamespace
        code = self.code_cells[-1]
        function = next(
            node for node in ast.parse(code).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "unload_local_models_with_retry"
        )
        attempts = []
        sleeps = []
        statuses = [(1, "LM Link connection closed: connector_closed"), (0, "")]
        def console(arguments, check=True):
            attempts.append((arguments, check))
            status, output = statuses.pop(0)
            return SimpleNamespace(returncode=status, stdout=output, args=arguments)
        namespace = {
            "run_console": console,
            "subprocess": __import__("subprocess"),
            "time": SimpleNamespace(sleep=sleeps.append)
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<notebook>", "exec"), namespace)
        namespace["unload_local_models_with_retry"]()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(
            attempts, [(["lms", "unload", "--all"], False)] * 2
        )
        self.assertEqual(sleeps, [2])

    def test_colab_unload_fails_fast_on_non_transient_error(self):
        from types import SimpleNamespace
        import subprocess
        code = self.code_cells[-1]
        function = next(
            node for node in ast.parse(code).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "unload_local_models_with_retry"
        )
        namespace = {
            "run_console": lambda args, check=True: SimpleNamespace(
                returncode=1, stdout="invalid option", args=args
            ),
            "subprocess": subprocess,
            "time": SimpleNamespace(sleep=lambda delay: self.fail("must not retry"))
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<notebook>", "exec"), namespace)
        with self.assertRaises(subprocess.CalledProcessError):
            namespace["unload_local_models_with_retry"]()

    def test_colab_unload_stops_after_retry_limit(self):
        from types import SimpleNamespace
        code = self.code_cells[-1]
        function = next(
            node for node in ast.parse(code).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "unload_local_models_with_retry"
        )
        sleeps = []
        namespace = {
            "run_console": lambda args, check=True: SimpleNamespace(
                returncode=1, stdout="connector_closed", args=args
            ),
            "subprocess": __import__("subprocess"),
            "time": SimpleNamespace(sleep=sleeps.append)
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<notebook>", "exec"), namespace)
        with self.assertRaisesRegex(RuntimeError, "2回連続"):
            namespace["unload_local_models_with_retry"](max_attempts=2)
        self.assertEqual(sleeps, [2])

    def test_model_lookup_matches_exact_size_and_quantization(self):
        code = self.code_cells[-1]
        function = next(
            node for node in ast.parse(code).body
            if isinstance(node, ast.FunctionDef) and node.name == "resolve_local_model_key"
        )
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<notebook>", "exec"), namespace)
        resolve = namespace["resolve_local_model_key"]
        inventory = [
            {"type": "llm", "key": "pfnet/plamo-3-translate-8b",
             "format": "gguf", "quantization": {"name": "Q4_K_M"},
             "size_bytes": 5280, "selected_variant": "pfnet/plamo-3-translate-8b@q4_k_m",
             "variants": ["pfnet/plamo-3-translate-8b@q4_k_m"]},
            {"type": "llm", "key": "pfnet/plamo-3-translate-8b-q3",
             "format": "gguf", "quantization": {"name": "Q3_K_M"},
             "size_bytes": 4310},
            {"type": "llm", "key": "other/model", "format": "gguf",
             "quantization": {"name": "Q4_K_M"}, "size_bytes": 5280}
        ]
        self.assertEqual(
            resolve(inventory, "8b", "Q4_K_M", 5280),
            "pfnet/plamo-3-translate-8b@q4_k_m"
        )
        with self.assertRaisesRegex(RuntimeError, "一意に特定"):
            resolve(inventory, "8b", "Q4_K_M", 5279)
        with self.assertRaisesRegex(RuntimeError, "一意に特定"):
            resolve(inventory + [inventory[0]], "8b", "Q4_K_M", 5280)
        with self.assertRaisesRegex(RuntimeError, "一意に特定"):
            resolve(inventory, "8b", "Q2_K", 5280)

    def test_only_valid_quantization_combination(self):
        source = self.code_cells[-1]
        self.assertIn('plamo_size = "8b"', self.find_code('USE_GOOGLE_DRIVE = True'))
        self.assertIn('if quantization not in OFFICIAL_GGUF_FORMATS[plamo_size]:', source)
        self.assertIn('model_id = f"plamo-3-translate-{plamo_size}"', source)
        self.assertNotIn('model_id = f"plamo-3-translate-{plamo_size}-colab"', source)


if __name__ == "__main__":
    unittest.main()
