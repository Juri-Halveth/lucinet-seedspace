import http.client
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("molecular_server", ROOT / "serve.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.lab = module.Lab(Path(cls.tmp.name) / "state")
        cls.server = module.make_server(cls.lab)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host = f"127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=20)
        hs = {"Host": self.host, "Origin": "http://" + self.host, "Content-Type": "application/json"}
        hs.update(headers or {})
        conn.request(method, path, body, hs)
        response = conn.getresponse()
        raw = response.read()
        status, content_type = response.status, response.getheader("Content-Type")
        conn.close()
        return status, raw, content_type

    def fixture(self, step=32):
        result = subprocess.run([self.lab.node, str(ROOT / "validate.mjs"), "--fixture"],
            input=json.dumps({"config": {"scenario": "catalase", "gate": "open", "seed": 127}, "step": step}).encode(),
            check=True, capture_output=True)
        return result.stdout

    def test_save_readback_verify_and_idempotent_retry(self):
        raw = self.fixture()
        code, data, _ = self.request("POST", "/api/checkpoints", raw)
        self.assertEqual(code, 200, data)
        receipt = json.loads(data)
        self.assertTrue(receipt["verify"])
        self.assertFalse(receipt["alreadySaved"])
        self.assertEqual(receipt["step"], 32)
        source = self.lab.work.store.source_by_id(receipt["sourceId"])
        stored = self.lab.work.read_object(source)
        self.assertEqual(json.loads(stored), json.loads(raw))
        before = self.lab.work.store.latest_ledger()["entry_hash"]
        code, second, _ = self.request("POST", "/api/checkpoints", raw)
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(second)["alreadySaved"])
        self.assertEqual(before, self.lab.work.store.latest_ledger()["entry_hash"])
        self.assertTrue(self.lab.work.verify()["ok"])
        code, loaded, _ = self.request("GET", "/api/checkpoints/" + receipt["packetDigest"])
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(loaded), json.loads(raw))
        self.assertIn(receipt["packetDigest"], [r["packetDigest"] for r in self.lab.status()["checkpoints"]])

    def test_tampered_snapshot_rejected_before_any_source_write(self):
        packet = json.loads(self.fixture())
        packet["snapshot"]["active"][0]["position"]["x"] = 999
        before = len(self.lab.work.store.sources())
        code, _, _ = self.request("POST", "/api/checkpoints", json.dumps(packet))
        self.assertEqual(code, 400)
        self.assertEqual(len(self.lab.work.store.sources()), before)

    def test_cross_origin_and_rebound_host_rejected(self):
        self.assertEqual(self.request("GET", "/", headers={"Host": "foreign.invalid"})[0], 403)
        self.assertEqual(self.request("POST", "/api/checkpoints", "{}", {"Origin": "https://foreign.invalid"})[0], 403)

    def test_serving_whitelist_never_exposes_workspace_code_or_paths(self):
        for path in ["/.nova/ledger.jsonl", "/serve.py", "/../PREDECESSOR.json", "/data/../../serve.py", "/%2e%2e/serve.py"]:
            self.assertEqual(self.request("GET", path)[0], 404)
        code, body, mime = self.request("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", mime)
        self.assertIn(b"Molek", body)
        for address in ["../serve.py", "0" * 64, "ledger", "..%2fPREDECESSOR.json"]:
            self.assertEqual(self.request("GET", "/api/checkpoints/" + address)[0], 404)

    def test_body_types_duplicates_and_limits_rejected(self):
        for body, headers, expected in [("{}", {"Content-Type": "text/plain"}, 415),
                                        ('{"schema":"x","schema":"y"}', {}, 400),
                                        ("{}", {"Content-Length": str(module.MAX_BODY + 1)}, 413)]:
            self.assertEqual(self.request("POST", "/api/checkpoints", body, headers)[0], expected)

    def test_status_is_minimized_and_runtime_bound(self):
        code, raw, _ = self.request("GET", "/api/status")
        self.assertEqual(code, 200)
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertEqual(data["version"], "2.1.2")
        self.assertNotIn(self.tmp.name, raw.decode())


if __name__ == "__main__":
    unittest.main(verbosity=2)
