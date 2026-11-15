import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mod_translator import ModTranslator
from plamo_hosts import available_plamo_hosts, loaded_plamo_info, parse_plamo_hosts


HOSTS = ["http://127.0.0.1:1234", "http://100.64.0.2:1234"]
MODEL_ID = "plamo-3-translate-8b"
MODEL_KEY = "pfnet/plamo-3-translate-8b-GGUF"


def model_info(identifier=MODEL_ID, key=MODEL_KEY, quant="Q4_K_M"):
    return {
        "type": "llm", "key": key, "quantization": {"name": quant},
        "size_bytes": 5280, "loaded_instances": [{"id": identifier}]
    }


class PLaMoHostTests(unittest.TestCase):
    def test_hosts_are_parsed_as_distinct_servers(self):
        self.assertEqual(
            parse_plamo_hosts("http://127.0.0.1:1234/, https://100.64.0.2:1234/"),
            ["http://127.0.0.1:1234", "https://100.64.0.2:1234"]
        )
        for bad in [
            "localhost:1234", "http://host:1234/api/v1/models",
            "http://user:pass@host:1234", "http://host:1234,http://host:1234",
            "http://host:1234,", "http://host:1234?x=y"
        ]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_plamo_hosts(bad)

    @patch("plamo_hosts.requests.get")
    def test_probes_same_identifier_without_renaming(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {"models": [model_info()]}
        get.return_value = response
        self.assertEqual(
            loaded_plamo_info(HOSTS[0], MODEL_ID)["key"], MODEL_KEY
        )
        self.assertEqual(
            get.call_args.args[0], HOSTS[0] + "/api/v1/models"
        )

    @patch("plamo_hosts.loaded_plamo_info")
    def test_only_available_matching_gguf_hosts_are_selected(self, probe):
        probe.side_effect = [
            model_info(), None
        ]
        available, signature = available_plamo_hosts(HOSTS, MODEL_ID)
        self.assertEqual(available, [HOSTS[0]])
        self.assertEqual(signature, (MODEL_KEY, "Q4_K_M", 5280))
        probe.side_effect = [
            model_info(), model_info(quant="Q3_K_M")
        ]
        with self.assertRaisesRegex(RuntimeError, "一致しません"):
            available_plamo_hosts(HOSTS, MODEL_ID)
        probe.side_effect = [model_info(), model_info(key="different/8b")]
        with self.assertRaisesRegex(RuntimeError, "一致しません"):
            available_plamo_hosts(HOSTS, MODEL_ID)

    @patch("plamo_hosts.loaded_plamo_info")
    def test_new_host_becomes_available_on_later_probe(self, probe):
        probe.side_effect = [model_info(), None, model_info(), model_info()]
        first, signature = available_plamo_hosts(HOSTS, MODEL_ID)
        second, _ = available_plamo_hosts(HOSTS, MODEL_ID, signature)
        self.assertEqual(first, [HOSTS[0]])
        self.assertEqual(second, HOSTS)

    @patch("plamo_hosts.loaded_plamo_info")
    def test_disconnected_server_does_not_hide_healthy_peer(self, probe):
        import requests
        probe.side_effect = [
            requests.ConnectionError("connection closed"), model_info()
        ]
        available, signature = available_plamo_hosts(HOSTS, MODEL_ID)
        self.assertEqual(available, [HOSTS[1]])
        self.assertEqual(signature[0], MODEL_KEY)

    @patch("plamo_hosts.loaded_plamo_info", return_value=model_info())
    @patch("mod_translator.requests.post")
    def test_same_identifier_reaches_two_distinct_endpoints_in_parallel(self, post, probe):
        barrier = threading.Barrier(2, timeout=3)
        reached = []
        lock = threading.Lock()

        def reply(url, json, timeout):
            with lock:
                reached.append((url, json["model"]))
            barrier.wait()
            response = Mock(status_code=200, text="")
            response.json.return_value = {
                "choices": [{"text": "日本語", "finish_reason": "stop"}]
            }
            return response

        post.side_effect = reply
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mods = root / "mods"
            mods.mkdir()
            with zipfile.ZipFile(mods / "test.jar", "w") as archive:
                archive.writestr(
                    "assets/example/lang/en_us.json",
                    json.dumps({"item.a": "Stone", "item.b": "Wood"})
                )
            args = SimpleNamespace(
                input=str(mods), output=str(root / "output"),
                engine="plamo", key=None, model=MODEL_ID,
                plamo_models=None, plamo_hosts=",".join(HOSTS),
                exclude_devices=None, plamo_api_url=HOSTS[0] + "/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=0,
                gemma_only=False, force=False, repair_model=None,
                repair_api_url=HOSTS[0] + "/v1/chat/completions",
                model_load_policy="wait", workers=2
            )
            translator = ModTranslator(args)
            self.assertTrue(translator.plamo_pool_from_hosts)
            self.assertEqual(translator.plamo_models, [MODEL_ID])
            translator.run()
            self.assertCountEqual(reached, [
                (HOSTS[0] + "/v1/completions", MODEL_ID),
                (HOSTS[1] + "/v1/completions", MODEL_ID)
            ])
            self.assertEqual(len(translator.plamo_cache), 2)
            self.assertEqual(
                translator.get_plamo_translation(
                    "test.jar", "assets/example/lang/en_us.json", "item.a", "Stone"
                ), "日本語"
            )

    @patch("plamo_hosts.loaded_plamo_info", return_value=model_info())
    @patch("mod_translator.require_loaded_lm_studio_model", return_value="lfm")
    def test_lfm_remains_separate_from_direct_plamo_hosts(self, require, probe):
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(
                input=folder, output=folder, engine="plamo", key=None,
                model=MODEL_ID, plamo_models=None, plamo_hosts=",".join(HOSTS),
                exclude_devices=None, plamo_api_url=HOSTS[0] + "/v1/completions",
                plamo_form="plain", plamo_glossary=None, plamo_context="",
                plamo_context_file=None, plamo_history=0,
                gemma_only=False, force=False, repair_model="lfm",
                repair_api_url=HOSTS[0] + "/v1/chat/completions",
                model_load_policy="wait", workers=2
            )
            ModTranslator(args)
            require.assert_called_once_with(
                "lfm", HOSTS[0] + "/v1/chat/completions", "wait"
            )


if __name__ == "__main__":
    unittest.main()
