import ast
import json
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

    def test_download_uses_official_exact_gguf_and_resumes(self):
        code = self.code_cells[-1]
        self.assertIn('f"plamo-3-translate-{plamo_size}-{quantization}.gguf"', code)
        self.assertIn("https://huggingface.co/pfnet/", code)
        self.assertIn('"--continue-at", "-"', code)
        self.assertIn("os.replace(partial_path, model_path)", code)
        self.assertIn('"lms", "load"', code)
        self.assertNotIn('"lms", "get"', code)
        self.assertNotIn('subprocess.DEVNULL)', code)

    def test_auth_vault_encrypts_before_saving_to_drive(self):
        code = self.code_cells[2]
        self.assertIn('AESGCM(vault_key(salt)).encrypt(', code)
        self.assertIn('AESGCM(vault_key(salt)).decrypt(', code)
        self.assertIn('LM_LINK_VAULT_PASSWORD', code)
        self.assertIn('getpass.getpass(', code)
        self.assertIn('AUTH_DIRS = ("credentials", "hub")', code)
        self.assertIn('VAULT.with_suffix(".tmp")', code)
        self.assertIn('os.replace(temp_path, VAULT)', code)
        self.assertNotIn('print(vault_password)', code)

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
