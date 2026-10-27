from __future__ import annotations

import errno
import hashlib
import json
import mimetypes
import os
import tempfile
import time
from contextlib import contextmanager
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .jsonutil import canonical_json, sha256_bytes, sha256_json, strict_loads
from .model import RELATION_STATES, RELATION_TYPES, SOURCE_STATUSES, RelationRecord, SourceEvent, SourceRecord

WORKSPACE_CONTRACT = "halveth.nova.workspace.v1"
LEDGER_CONTRACT = "halveth.nova.ledger.v1"
RESUME_CONTRACT = "halveth.nova.resume.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = canonical_json(value).encode("utf-8") + b"\n"
    with path.open("ab") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = strict_loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{i}: expected JSON object")
        out.append(value)
    return out


class NovaStore:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.nova = self.root / ".nova"
        self.objects = self.nova / "objects"
        self.sources_path = self.nova / "sources.jsonl"
        self.source_events_path = self.nova / "source-events.jsonl"
        self.relations_path = self.nova / "relations.jsonl"
        self.ledger_path = self.nova / "ledger.jsonl"
        self.resume_path = self.nova / "resume.json"
        self.config_path = self.nova / "config.json"
        self.lock_path = self.nova / "write.lock"

    @contextmanager
    def write_lock(self, timeout: float = 8.0, stale_after: float = 120.0):
        # Keep the inode/file identity stable. Kernel locks are released on process
        # exit, and a live owner never loses its lock merely because time passed.
        # stale_after remains accepted for callers of the 1.2.0 API; it no longer
        # expires a lock. All concurrent processes must use this lock protocol.
        self.nova.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        with self.lock_path.open("a+b") as handle:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            if os.name == "nt":
                import msvcrt
                def acquire():
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                def release():
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                def acquire():
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                def release():
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            while True:
                try:
                    acquire()
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    if time.monotonic() >= deadline:
                        raise RuntimeError("WORKSPACE_BUSY") from error
                    time.sleep(0.05)
            try:
                yield
            finally:
                release()

    def init(self, name: str | None = None) -> dict[str, Any]:
        with self.write_lock():
            self.objects.mkdir(parents=True, exist_ok=True)
            if self.config_path.exists():
                return self.read_config()
            cfg = {
                "contract": WORKSPACE_CONTRACT,
                "name": name or self.root.name,
                "created_at": utc_now(),
                "runtime": "halveth-nova",
            }
            atomic_write(self.config_path, (canonical_json(cfg) + "\n").encode("utf-8"))
            return cfg

    def require(self) -> None:
        if not self.config_path.is_file():
            raise RuntimeError(f"not a NOVA workspace: {self.root}; run `nova init`")
        self.read_config()

    def read_config(self) -> dict[str, Any]:
        cfg = strict_loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict) or cfg.get("contract") != WORKSPACE_CONTRACT:
            raise ValueError("invalid NOVA workspace contract")
        return cfg

    def sources(self) -> list[dict[str, Any]]:
        return load_jsonl(self.sources_path)

    def source_events(self) -> list[dict[str, Any]]:
        return load_jsonl(self.source_events_path)

    def relations(self) -> list[dict[str, Any]]:
        return load_jsonl(self.relations_path)

    def ledger(self) -> list[dict[str, Any]]:
        return load_jsonl(self.ledger_path)

    def status_map(self) -> dict[str, dict[str, Any]]:
        statuses = {s["source_id"]: {"status": "active", "at": s["added_at"], "note": "", "superseded_by": None} for s in self.sources()}
        for event in self.source_events():
            if event["source_id"] not in statuses:
                raise ValueError(f"status event references missing source {event['source_id']}")
            statuses[event["source_id"]] = {
                "status": event["status"], "at": event["at"], "note": event.get("note", ""),
                "superseded_by": event.get("superseded_by"),
            }
        return statuses

    def source_by_id(self, source_id: str) -> dict[str, Any]:
        for row in self.sources():
            if row["source_id"] == source_id:
                return row
        raise KeyError(source_id)

    def _locator_for(self, file: Path, input_root: Path) -> str:
        try:
            return str(file.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            root_basis = str(input_root.resolve()).encode("utf-8")
            root_tag = sha256_bytes(root_basis)[:12]
            if input_root.is_dir():
                rel = file.relative_to(input_root).as_posix()
            else:
                rel = file.name
            return f"external/{root_tag}/{rel}"

    def _record_source(self, locator: str, data: bytes, tags: list[str], metadata: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        digest = sha256_bytes(data)
        source_id = "src_" + sha256_bytes((locator + "\0" + digest).encode("utf-8"))[:20]
        existing = self.sources()
        for row in existing:
            if row["source_id"] == source_id:
                statuses = self.status_map()
                for old in existing:
                    if (old["locator"] == locator and old["source_id"] != source_id
                            and statuses[old["source_id"]]["status"] in {"active", "historical"}):
                        self._set_status_unlocked(old["source_id"], "superseded",
                                                  note=f"locator restored to {source_id}", superseded_by=source_id)
                if statuses[source_id]["status"] == "superseded":
                    self._set_status_unlocked(source_id, "active", note="locator restored to stored source bytes")
                return row, False
        previous = [r for r in existing if r["locator"] == locator]
        media_type = mimetypes.guess_type(locator)[0] or "application/octet-stream"
        rec = SourceRecord(source_id, locator, digest, len(data), media_type, utc_now(), tags, metadata).to_dict()
        object_path = self.objects / digest
        if not object_path.exists():
            atomic_write(object_path, data)
        append_jsonl(self.sources_path, rec)
        for old in previous:
            current = self.status_map().get(old["source_id"], {"status": "active"})["status"]
            if current in {"active", "historical"} and old["digest"] != digest:
                self._set_status_unlocked(old["source_id"], "superseded", note=f"locator updated to {source_id}", superseded_by=source_id)
        return rec, True

    def ingest_path(self, path: Path | str, *, tags: list[str] | None = None, metadata: dict[str, Any] | None = None, max_bytes: int = 8_000_000) -> list[dict[str, Any]]:
        self.require()
        if type(max_bytes) is not int or max_bytes < 0:
            raise ValueError("max_bytes must be a nonnegative integer")
        p = Path(path).resolve()
        tags = list(tags or [])
        metadata = dict(metadata or {})
        if not p.exists():
            raise FileNotFoundError(p)
        if p.is_dir():
            files = sorted(x for x in p.rglob("*") if x.is_file() and ".nova" not in x.parts and ".git" not in x.parts)
        else:
            files = [p]
        results: list[dict[str, Any]] = []
        with self.write_lock():
            for f in files:
                locator = self._locator_for(f, p)
                size = f.stat().st_size
                if size > max_bytes:
                    results.append({"locator": locator, "skipped": "MAX_BYTES", "bytes": size})
                    continue
                with f.open("rb") as source:
                    data = source.read(max_bytes + 1)
                if len(data) > max_bytes:
                    results.append({"locator": locator, "skipped": "MAX_BYTES", "bytes": max(len(data), f.stat().st_size)})
                    continue
                rec, created = self._record_source(locator, data, tags, metadata)
                results.append({**rec, "created": created})
        return results

    def ingest_bytes(self, locator: str, data: bytes, *, tags: list[str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        self.require()
        with self.write_lock():
            rec, created = self._record_source(locator, data, list(tags or []), dict(metadata or {}))
            return {**rec, "created": created}

    def _set_status_unlocked(self, source_id: str, status: str, *, note: str = "", superseded_by: str | None = None) -> dict[str, Any]:
        self.source_by_id(source_id)
        if status not in SOURCE_STATUSES:
            raise ValueError(f"invalid source status: {status}")
        if superseded_by is not None:
            self.source_by_id(superseded_by)
        event = SourceEvent(event_id="sev_" + uuid.uuid4().hex, source_id=source_id, status=status, at=utc_now(), note=note, superseded_by=superseded_by).to_dict()
        append_jsonl(self.source_events_path, event)
        return event

    def set_status(self, source_id: str, status: str, *, note: str = "", superseded_by: str | None = None) -> dict[str, Any]:
        self.require()
        with self.write_lock():
            return self._set_status_unlocked(source_id, status, note=note, superseded_by=superseded_by)

    def add_relation(self, subject: str, predicate: str, object_: str, state: str, evidence: list[str], note: str = "") -> dict[str, Any]:
        self.require()
        if predicate not in RELATION_TYPES:
            raise ValueError(f"invalid relation type: {predicate}")
        if state not in RELATION_STATES:
            raise ValueError(f"invalid relation state: {state}")
        source_ids = {s["source_id"] for s in self.sources()}
        for sid in evidence:
            if sid not in source_ids:
                raise ValueError(f"relation evidence source missing: {sid}")
        with self.write_lock():
            relation = RelationRecord(relation_id="rel_" + uuid.uuid4().hex, subject=subject, predicate=predicate, object=object_, state=state, created_at=utc_now(), evidence=evidence, note=note).to_dict()
            append_jsonl(self.relations_path, relation)
            return relation

    def latest_ledger(self) -> dict[str, Any] | None:
        rows = self.ledger()
        return rows[-1] if rows else None

    def append_receipt(self, receipt: dict[str, Any], *, expected_previous_hash: str | None = None) -> dict[str, Any]:
        self.require()
        with self.write_lock():
            rows = self.ledger()
            previous = rows[-1]["entry_hash"] if rows else None
            if expected_previous_hash is not None and expected_previous_hash != previous:
                raise RuntimeError("STALE_PREDECESSOR")
            if receipt.get("predecessor_entry_hash") != previous:
                raise RuntimeError("STALE_PREDECESSOR")
            seq = len(rows) + 1
            envelope = {"contract": LEDGER_CONTRACT, "sequence": seq, "previous_hash": previous, "receipt": receipt}
            envelope["entry_hash"] = sha256_json(envelope)
            append_jsonl(self.ledger_path, envelope)
            resume = self._resume_for(envelope)
            atomic_write(self.resume_path, (canonical_json(resume) + "\n").encode("utf-8"))
            return envelope

    @staticmethod
    def _resume_for(envelope: dict[str, Any]) -> dict[str, Any]:
        receipt = envelope["receipt"]
        return {"contract": RESUME_CONTRACT, "sequence": envelope["sequence"],
                "entry_hash": envelope["entry_hash"], "run_id": receipt["run_id"],
                "next_seed": receipt.get("next_seed", ""), "updated_at": receipt["created_at"]}

    def read_resume(self) -> dict[str, Any] | None:
        if not self.resume_path.exists():
            return None
        value = strict_loads(self.resume_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("contract") != RESUME_CONTRACT:
            raise ValueError("invalid resume contract")
        return value

    def verify(self) -> dict[str, Any]:
        self.require()
        errors: list[str] = []
        source_ids: set[str] = set()
        source_map: dict[str, dict[str, Any]] = {}
        for s in self.sources():
            if s["source_id"] in source_ids:
                errors.append(f"duplicate source_id {s['source_id']}")
            source_ids.add(s["source_id"])
            source_map[s["source_id"]] = s
            if not isinstance(s.get("digest"), str) or len(s["digest"]) != 64 or any(c not in "0123456789abcdef" for c in s["digest"]):
                errors.append(f"invalid object digest {s['source_id']}")
                continue
            obj = self.objects / s["digest"]
            if not obj.is_file():
                errors.append(f"missing object {s['digest']}")
            elif sha256_bytes(obj.read_bytes()) != s["digest"]:
                errors.append(f"object digest mismatch {s['source_id']}")
            elif obj.stat().st_size != s["byte_length"]:
                errors.append(f"object byte length mismatch {s['source_id']}")
        try:
            self.status_map()
        except Exception as e:
            errors.append(str(e))
        def check_evidence(evidence, context):
            if not isinstance(evidence, list):
                errors.append(f"{context}: invalid evidence list")
                return
            for sid in evidence:
                if not isinstance(sid, str) or sid not in source_ids:
                    errors.append(f"{context}: missing source {sid}")
        relations = self.relations()
        relation_ids = set()
        for relation in relations:
            rid = relation.get("relation_id")
            if not isinstance(rid, str) or rid in relation_ids:
                errors.append("invalid or duplicate relation_id")
            else:
                relation_ids.add(rid)
            check_evidence(relation.get("evidence", []), f"relation {rid}")
        previous = None
        rows = self.ledger()
        for index, row in enumerate(rows, 1):
            if row.get("contract") != LEDGER_CONTRACT:
                errors.append(f"ledger {index}: invalid contract")
                continue
            if row.get("sequence") != index:
                errors.append(f"ledger {index}: invalid sequence")
            if row.get("previous_hash") != previous:
                errors.append(f"ledger {index}: previous hash mismatch")
            candidate = dict(row)
            got = candidate.pop("entry_hash", None)
            expected = sha256_json(candidate)
            if got != expected:
                errors.append(f"ledger {index}: entry hash mismatch")
            receipt = row.get("receipt")
            if not isinstance(receipt, dict):
                errors.append(f"ledger {index}: invalid receipt")
                previous = got
                continue
            inputs = receipt.get("input_sources", [])
            if not isinstance(inputs, list):
                errors.append(f"ledger {index}: invalid input_sources")
                inputs = []
            for binding in inputs:
                if not isinstance(binding, dict):
                    errors.append(f"ledger {index}: invalid source binding")
                    continue
                sid = binding.get("source_id")
                check_evidence([sid], f"ledger {index} input")
                source = source_map.get(sid) if isinstance(sid, str) else None
                if source and (binding.get("digest") != source["digest"] or binding.get("locator") != source["locator"]):
                    errors.append(f"ledger {index}: source binding mismatch {sid}")
            claims = receipt.get("claims", [])
            if not isinstance(claims, list):
                errors.append(f"ledger {index}: invalid claims")
                claims = []
            for claim in claims:
                if not isinstance(claim, dict):
                    errors.append(f"ledger {index}: invalid claim")
                else:
                    check_evidence(claim.get("evidence", []), f"ledger {index} claim")
            visible = receipt.get("relations_visible", [])
            if not isinstance(visible, list):
                errors.append(f"ledger {index}: invalid relations_visible")
                visible = []
            for rid in visible:
                if not isinstance(rid, str) or rid not in relation_ids:
                    errors.append(f"ledger {index}: missing relation {rid}")
            previous = got
        resume = self.read_resume()
        if rows:
            if not resume:
                errors.append("ledger exists but resume missing")
            elif resume.get("sequence") != len(rows) or resume.get("entry_hash") != rows[-1].get("entry_hash"):
                errors.append("resume is stale")
            else:
                try:
                    if canonical_json(resume) != canonical_json(self._resume_for(rows[-1])):
                        errors.append("resume continuation does not match latest receipt")
                except (KeyError, TypeError, ValueError):
                    errors.append("invalid continuation receipt")
        elif resume:
            errors.append("resume exists without ledger")
        return {"ok": not errors, "errors": errors, "source_count": len(source_ids), "relation_count": len(relations), "ledger_count": len(rows), "latest_hash": previous}

    def export_zip(self, target: Path | str) -> dict[str, Any]:
        import zipfile
        self.require()
        target = Path(target).resolve()
        if target == self.nova or self.nova in target.parents:
            raise ValueError("export target must be outside .nova")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.write_lock():
            verification = self.verify()
            if not verification["ok"]:
                raise RuntimeError("workspace verification failed before export: " + "; ".join(verification["errors"]))
            files = sorted(p for p in self.nova.rglob("*") if p.is_file() and p != self.lock_path)
            resume = self.read_resume()
            config = self.read_config()
            manifest = {"contract": "halveth.nova.export.v1", "workspace": config["name"], "state_at": (resume or config)["updated_at" if resume else "created_at"], "files": []}
            fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
            os.close(fd)
            try:
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                    def add(name, data):
                        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                        info.compress_type = zipfile.ZIP_DEFLATED
                        info.external_attr = 0o644 << 16
                        z.writestr(info, data)
                    for p in files:
                        rel = p.relative_to(self.root).as_posix()
                        data = p.read_bytes()
                        manifest["files"].append({"path": rel, "bytes": len(data), "sha256": sha256_bytes(data)})
                        add(rel, data)
                    add("NOVA_EXPORT_MANIFEST.json", (canonical_json(manifest) + "\n").encode("utf-8"))
                with open(temporary, "rb") as archive:
                    digest = hashlib.file_digest(archive, "sha256").hexdigest()
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {"path": str(target), "sha256": digest, "files": len(files), "manifest": manifest}
