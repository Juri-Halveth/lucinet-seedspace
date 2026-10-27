"""Loopback-only lab + bounded NOVA checkpoint bridge. Python 3.11+ and Node 22+."""
from __future__ import annotations
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "src"))
from halveth_nova import __version__
from halveth_nova.jsonutil import canonical_json, strict_loads
from halveth_nova.store import atomic_write, utc_now
from halveth_nova.workbench.controller import Workbench

MAX_BODY = 512_000
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.mjs": ("app.mjs", "text/javascript; charset=utf-8"),
    "/engine.mjs": ("engine.mjs", "text/javascript; charset=utf-8"),
    "/data/sources.json": ("data/sources.json", "application/json; charset=utf-8")}


class Lab:
    def __init__(self, workspace: Path, node: str = "node"):
        self.workspace = workspace.resolve()
        if self.workspace.is_relative_to(ROOT) or ROOT.is_relative_to(self.workspace):
            raise ValueError("WORKSPACE_MUST_BE_SEPARATE_FROM_SERVED_CODE")
        self.node = shutil.which(node)
        if not self.node:
            raise RuntimeError("NODE_REQUIRED_FOR_MODEL_REPLAY")
        self.lock = threading.Lock()
        self.work = Workbench(self.workspace)
        self.work.store.init("NOVA Molecular Lineage")
        base = self.work.store.verify()
        if not base["ok"]:
            raise ValueError("PREDECESSOR_INVALID")
        # 2.1.2 migrates stale derived analyses in this candidate workspace only.
        self.work.compile_sources()
        if not self.work.verify()["ok"]:
            raise ValueError("WORKSPACE_VERIFICATION_FAILED")
        self.receipts = self.workspace / "molecular-receipts"
        self.receipts.mkdir(exist_ok=True)
        self.runs = self.workspace / "molecular-runs"
        self.runs.mkdir(exist_ok=True)
        predecessor = self.workspace / "PREDECESSOR.json"
        self.predecessor = json.loads(predecessor.read_text(encoding="utf-8")) if predecessor.exists() else {}
        self.model_source = self.work.store.ingest_bytes("molecular-lab/engine.mjs", (ROOT / "engine.mjs").read_bytes(),
            tags=["molecular-model"], metadata={"data_class": "PUBLIC", "state": "DECLARED_MODEL_CODE_NOT_SOURCE_EXECUTION"})
        self.chemical_source = self.work.store.ingest_bytes("molecular-lab/sources.json", (ROOT / "data/sources.json").read_bytes(),
            tags=["molecular-sources"], metadata={"data_class": "PUBLIC", "state": "PUBLIC_SOURCE_PROJECTION"})
        for source in json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))["receipts"]:
            raw = (ROOT / "data" / source["file"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != source["sha256"] or len(raw) != source["bytes"]:
                raise ValueError("CHEMICAL_SOURCE_BYTES_CHANGED")
            self.work.store.ingest_bytes("molecular-lab/" + source["file"], raw,
                tags=["pubchem-raw"], metadata={"data_class": "PUBLIC", "url": source["url"], "received_at": source["receivedAt"]})

    def status(self):
        with self.lock:
            self.verify_model_epoch()
            verification = self.work.verify()
            return {"ok": verification["ok"], "version": __version__,
                "ledgerCount": verification.get("ledger_count", 0),
                "sourceCount": len(self.work.store.sources()),
                "latestHash": verification.get("latest_hash"),
                "predecessorHash": self.predecessor.get("latestHash"),
                "checkpoints": self.checkpoints()}

    def checkpoints(self):
        records = []
        for path in self.receipts.glob("*.json"):
            record = strict_loads(path.read_text(encoding="utf-8"))
            records.append({key: record[key] for key in ["packetDigest", "step", "sourceId", "entryHash", "sequence", "recordedAt"]})
        return sorted(records, key=lambda r: (r["sequence"], r["packetDigest"]), reverse=True)[:20]

    def read_checkpoint(self, digest):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("INVALID_CHECKPOINT_ADDRESS")
        with self.lock:
            self.verify_model_epoch()
            path = self.receipts / (digest + ".json")
            if not path.is_file():
                raise FileNotFoundError("CHECKPOINT_NOT_FOUND")
            receipt = strict_loads(path.read_text(encoding="utf-8"))
            source = self.work.store.source_by_id(receipt["sourceId"])
            if source["digest"] != receipt["sourceDigest"] or source.get("metadata", {}).get("model_state") != "DECLARED_EDUCATIONAL_MODEL":
                raise ValueError("CHECKPOINT_SOURCE_BINDING_CHANGED")
            raw = self.work.read_object(source)
            packet = strict_loads(raw.decode("utf-8"))
            if packet["packetDigest"] != digest:
                raise ValueError("CHECKPOINT_RECEIPT_CHANGED")
            return raw

    def verify_model_epoch(self):
        for file, record in [(ROOT / "engine.mjs", self.model_source), (ROOT / "data/sources.json", self.chemical_source)]:
            if hashlib.sha256(file.read_bytes()).hexdigest() != record["digest"]:
                raise RuntimeError("MODEL_EPOCH_CHANGED_RESTART_SERVER")

    def save(self, raw: bytes):
        if len(raw) > MAX_BODY:
            raise ValueError("BODY_LIMIT")
        packet = strict_loads(raw.decode("utf-8"))
        if not isinstance(packet, dict) or packet.get("schema") != "molecular-checkpoint.v1":
            raise ValueError("CHECKPOINT_REQUIRED")
        self.verify_model_epoch()
        # Own fixed interpreter + own fixed verifier; supplied records are stdin data.
        result = subprocess.run([self.node, str(ROOT / "validate.mjs")],
            input=canonical_json(packet).encode("utf-8"), capture_output=True, timeout=15, cwd=ROOT)
        if result.returncode or not json.loads(result.stdout).get("ok"):
            raise ValueError("MODEL_REPLAY_OR_DIGEST_REJECTED")
        digest = packet["packetDigest"]
        serialized = (canonical_json(packet) + "\n").encode("utf-8")
        with self.lock:
            verification = self.work.verify()
            if not verification["ok"]:
                raise ValueError("WORKSPACE_INVALID_BEFORE_WRITE")
            path = self.receipts / (digest + ".json")
            if path.exists():
                receipt = strict_loads(path.read_text(encoding="utf-8"))
                source = self.work.store.source_by_id(receipt["sourceId"])
                if self.work.read_object(source) != serialized:
                    raise ValueError("PRIOR_CHECKPOINT_BYTES_CHANGED")
                return {**receipt, "alreadySaved": True}
            run_path = self.runs / (packet["run"]["runId"] + ".json")
            if run_path.exists() and strict_loads(run_path.read_text(encoding="utf-8"))["runDigest"] != packet["runDigest"]:
                raise ValueError("RUN_ID_ALREADY_BINDS_ANOTHER_PLAN")
            if len(list(self.receipts.glob("*.json"))) >= 200:
                raise ValueError("LOCAL_CHECKPOINT_BUDGET_200_REACHED")
            if not run_path.exists():
                atomic_write(run_path, (canonical_json({"runDigest": packet["runDigest"], "recordedAt": utc_now()}) + "\n").encode("utf-8"))
            source = self.work.store.ingest_bytes(f"molecular-lab/{packet['run']['runId']}/step-{packet['step']}.json", serialized,
                tags=["molecular-checkpoint", "modeled-history"],
                metadata={"data_class": "INTERNAL_PSEUDONYMIZED", "model_state": "DECLARED_EDUCATIONAL_MODEL",
                    "model_source_id": self.model_source["source_id"], "model_digest": self.model_source["digest"],
                    "chemical_source_id": self.chemical_source["source_id"], "chemical_digest": self.chemical_source["digest"],
                    "viewed_step": packet["step"], "full_plan_events": "DECLARED_NOT_REAL_OBSERVATIONS"})
            done = self.work.run(f"Molecular lineage {packet['run']['runId']} checkpoint step {packet['step']}; preserve atom identities and source provenance", mode="FLOW")
            after = self.work.verify()
            if not after["ok"] or self.work.read_object(self.work.store.source_by_id(source["source_id"])) != serialized:
                raise ValueError("POST_WRITE_VERIFICATION_FAILED")
            receipt = {"ok": True, "alreadySaved": False, "recordedAt": utc_now(), "version": __version__,
                "step": packet["step"], "packetDigest": digest, "sourceId": source["source_id"], "sourceDigest": source["digest"],
                "sourceBytes": source["byte_length"], "previousHash": verification["latest_hash"],
                "sequence": done["ledger"]["sequence"], "entryHash": done["ledger"]["entry_hash"],
                "verify": True, "claimCeiling": "STORED_MODEL_RECORD_NOT_EMPIRICAL_MOLECULAR_TRACK"}
            atomic_write(path, (canonical_json(receipt) + "\n").encode("utf-8"))
            return receipt


def make_server(lab: Lab, port: int = 0):
    class Handler(BaseHTTPRequestHandler):
        def headers_safe(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == expected

        def send(self, status, data, content_type="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.headers_safe():
                return self.send(403, {"error": "HOST_REJECTED"})
            path = urlsplit(self.path).path
            if path == "/api/status":
                try:
                    return self.send(200, lab.status())
                except Exception:
                    return self.send(503, {"ok": False, "error": "NOVA_VERIFICATION_FAILED"})
            if path.startswith("/api/checkpoints/"):
                try:
                    return self.send(200, lab.read_checkpoint(path.removeprefix("/api/checkpoints/")))
                except (ValueError, FileNotFoundError, KeyError):
                    return self.send(404, {"error": "CHECKPOINT_NOT_FOUND_OR_INVALID"})
            asset = ASSETS.get(path)
            if not asset:
                return self.send(404, {"error": "NOT_FOUND"})
            file = ROOT / asset[0]
            if not file.resolve().is_relative_to(ROOT) or file.is_symlink():
                return self.send(403, {"error": "ASSET_REJECTED"})
            return self.send(200, file.read_bytes(), asset[1])

        def do_POST(self):
            if not self.headers_safe() or self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
                return self.send(403, {"error": "ORIGIN_REJECTED"})
            if self.path != "/api/checkpoints":
                return self.send(404, {"error": "NOT_FOUND"})
            if self.headers.get("Content-Type") != "application/json" or self.headers.get("Transfer-Encoding"):
                return self.send(415, {"error": "JSON_ONLY"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_BODY:
                    return self.send(413, {"error": "BODY_LIMIT"})
                self.connection.settimeout(15)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("INCOMPLETE_BODY")
                return self.send(200, lab.save(raw))
            except (ValueError, UnicodeError, KeyError, TypeError):
                return self.send(400, {"ok": False, "error": "INVALID_OR_INCONSISTENT_MODEL_RECORD"})
            except (OSError, RuntimeError, subprocess.SubprocessError):
                return self.send(503, {"ok": False, "error": "NOVA_WRITE_INCOMPLETE_RETRY_SAME_RECORD"})

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--port", default=0, type=int)
    args = parser.parse_args()
    server = make_server(Lab(args.workspace), args.port)
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/", "nova": __version__, "state": "LOOPBACK_ONLY"}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
