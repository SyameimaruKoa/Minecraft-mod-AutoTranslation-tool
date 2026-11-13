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
        code = self.code_cells[1]
        self.assertIn('AESGCM(vault_key(salt)).encrypt(', code)
        self.assertIn('AESGCM(vault_key(salt)).decrypt(', code)
        self.assertIn('LM_LINK_VAULT_PASSWORD', code)
        self.assertIn('getpass.getpass(', code)
        self.assertIn('AUTH_DIRS = ("credentials", "hub")', code)
        self.assertIn('VAULT.with_suffix(".tmp")', code)
        self.assertIn('os.replace(temp_path, VAULT)', code)
        self.assertNotIn('print(vault_password)', code)

    def test_login_restore_order_and_no_committed_outputs(self):
        startup, restore, login, model = self.code_cells
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

    def test_only_valid_quantization_combination(self):
        source = self.code_cells[-1]
        self.assertIn('plamo_size not in ("0.8b", "2b")', source)
        self.assertIn('model_id = f"plamo-3-translate-{plamo_size}-colab"', source)


if __name__ == "__main__":
    unittest.main()
