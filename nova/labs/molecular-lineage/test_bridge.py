import http.client
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
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

    def fixture(self, step=32, config=None, options=None):
        result = subprocess.run([self.lab.node, str(ROOT / "validate.mjs"), "--fixture"],
            input=json.dumps({"config": config or {"scenario": "catalase", "gate": "open", "seed": 127},
                              "step": step, "options": options or {}}).encode(),
            check=True, capture_output=True)
        return result.stdout

    @staticmethod
    def file_hashes(root):
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file() and p.name != "write.lock"}

    def fork(self, old, new):
        return subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "prepare_continuity.py"),
                               "--predecessor", str(old), "--workspace", str(new)], capture_output=True, text=True)

    def test_fork_preserves_checkpoint_reopen_retry_and_run_binding(self):
        old = module.Lab(Path(self.tmp.name) / "fork-old")
        raw = self.fixture(17)
        receipt = old.save(raw)
        saved = old.read_checkpoint(receipt["packetDigest"])
        before = self.file_hashes(old.workspace)
        new = Path(self.tmp.name) / "fork-new"
        done = self.fork(old.workspace, new)
        self.assertEqual(done.returncode, 0, done.stderr)
        copied = module.Lab(new)
        self.assertIn(receipt["packetDigest"], [r["packetDigest"] for r in copied.status()["checkpoints"]])
        self.assertEqual(copied.read_checkpoint(receipt["packetDigest"]), saved)
        self.assertTrue(copied.save(raw)["alreadySaved"])
        packet = json.loads(raw)
        other = self.fixture(17, {"scenario": "catalase", "gate": "closed", "seed": 127},
                             {"runId": packet["run"]["runId"], "recordedAt": packet["run"]["recordedAt"]})
        with self.assertRaisesRegex(ValueError, "RUN_ID_ALREADY_BINDS_ANOTHER_PLAN"):
            copied.save(other)
        self.assertEqual(self.file_hashes(old.workspace), before)

    def test_fork_rejects_a_misbound_lab_receipt_before_creating_destination(self):
        old = module.Lab(Path(self.tmp.name) / "bad-fork-old")
        receipt = old.save(self.fixture())
        path = old.receipts / (receipt["packetDigest"] + ".json")
        broken = json.loads(path.read_bytes())
        broken["sourceDigest"] = "0" * 64
        path.write_text(json.dumps(broken), encoding="utf-8")
        before = self.file_hashes(old.workspace)
        new = Path(self.tmp.name) / "bad-fork-new"
        done = self.fork(old.workspace, new)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("LAB_RECEIPT_BINDING_INVALID", done.stderr)
        self.assertFalse(new.exists())
        self.assertEqual(self.file_hashes(old.workspace), before)

    def test_fork_of_core_workspace_without_lab_indexes_remains_supported(self):
        old = module.Workbench(Path(self.tmp.name) / "core-fork-old")
        old.store.init("core predecessor")
        old.store.ingest_bytes("example.txt", b"source-bound continuity\n")
        old.run("continuity", mode="FLOW")
        before = self.file_hashes(old.store.root)
        new = Path(self.tmp.name) / "core-fork-new"
        done = self.fork(old.store.root, new)
        self.assertEqual(done.returncode, 0, done.stderr)
        copied = module.Lab(new)
        self.assertTrue(copied.status()["ok"])
        self.assertEqual(copied.status()["checkpoints"], [])
        self.assertEqual(self.file_hashes(old.store.root), before)

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
