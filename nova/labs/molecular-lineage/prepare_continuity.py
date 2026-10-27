"""Fork an explicitly selected local NOVA workspace and prove exact ledger prefixes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "src"))
from halveth_nova.workbench.controller import Workbench
from halveth_nova.jsonutil import strict_loads


def lab_history(root, work):
    """Validate the optional lab indexes against their copied NOVA source/ledger."""
    files = {}
    runs, receipts = {}, {}
    for name, records, pattern in [
        ("molecular-runs", runs, r"mol_[0-9a-f]{32}"),
        ("molecular-receipts", receipts, r"[0-9a-f]{64}"),
    ]:
        folder = root / name
        if folder.is_symlink():
            raise ValueError("INVALID_LAB_HISTORY_DIRECTORY")
        if not folder.exists():
            continue
        if not folder.is_dir():
            raise ValueError("INVALID_LAB_HISTORY_DIRECTORY")
        for path in sorted(folder.iterdir()):
            if (not path.is_file() or path.is_symlink() or path.suffix != ".json"
                    or not re.fullmatch(pattern, path.stem) or path.stat().st_size > 8192):
                raise ValueError("INVALID_LAB_HISTORY_FILE")
            raw = path.read_bytes()
            record = strict_loads(raw.decode("utf-8"))
            if not isinstance(record, dict):
                raise ValueError("INVALID_LAB_HISTORY_RECORD")
            records[path.stem] = record
            files[path.relative_to(root)] = raw
    for run in runs.values():
        if not re.fullmatch(r"[0-9a-f]{64}", run.get("runDigest", "")):
            raise ValueError("LAB_RUN_BINDING_INVALID")
    ledger = work.store.ledger()
    for digest, receipt in receipts.items():
        source = work.store.source_by_id(receipt["sourceId"])
        raw = work.read_object(source)
        packet = strict_loads(raw.decode("utf-8"))
        sequence = receipt["sequence"]
        if (type(sequence) is not int or not 1 <= sequence <= len(ledger)
                or len(raw) > 512_000 or packet.get("schema") != "molecular-checkpoint.v1"):
            raise ValueError("LAB_RECEIPT_BINDING_INVALID")
        entry = ledger[sequence - 1]
        plan = runs.get(packet["run"]["runId"])
        if (receipt.get("ok") is not True or receipt.get("verify") is not True
                or receipt["packetDigest"] != digest or packet["packetDigest"] != digest
                or receipt["sourceDigest"] != source["digest"] or receipt["sourceBytes"] != len(raw)
                or source.get("metadata", {}).get("model_state") != "DECLARED_EDUCATIONAL_MODEL"
                or receipt["step"] != packet["step"] or entry["entry_hash"] != receipt["entryHash"]
                or entry["previous_hash"] != receipt["previousHash"]
                or not plan or plan["runDigest"] != packet["runDigest"]):
            raise ValueError("LAB_RECEIPT_BINDING_INVALID")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    old, new = args.predecessor.resolve(), args.workspace.resolve()
    if new.exists() or old == new or new.is_relative_to(old) or old.is_relative_to(new):
        raise ValueError("FRESH_SEPARATE_WORKSPACE_REQUIRED")
    prior = Workbench(old)
    before = prior.store.verify()
    if not before["ok"]:
        raise ValueError("PREDECESSOR_INVALID")
    history = lab_history(old, prior)
    files = {p.relative_to(old): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (old / ".nova").rglob("*") if p.is_file() and p.name != "write.lock"}
    files.update({name: hashlib.sha256(raw).hexdigest() for name, raw in history.items()})
    new.mkdir(parents=True)
    shutil.copytree(old / ".nova", new / ".nova", ignore=shutil.ignore_patterns("write.lock"))
    for name, raw in history.items():
        target = new / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(raw)
        if target.read_bytes() != raw:
            raise ValueError("LAB_HISTORY_COPY_DIFFERENCE")
    prefixes = {}
    for name in ["sources.jsonl", "source-events.jsonl", "relations.jsonl", "ledger.jsonl"]:
        path = old / ".nova" / name
        if path.exists():
            raw = path.read_bytes()
            if (new / ".nova" / name).read_bytes() != raw:
                raise ValueError("COPY_PREFIX_DIFFERENCE")
            prefixes[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    work = Workbench(new)
    migration = work.compile_sources()
    after = work.verify()
    if not after["ok"]:
        raise ValueError("CANDIDATE_MIGRATION_INVALID:" + str(after["errors"]))
    if lab_history(new, work) != history:
        raise ValueError("LAB_HISTORY_BINDING_CHANGED")
    for name, record in prefixes.items():
        if hashlib.sha256((new / ".nova" / name).read_bytes()[:record["bytes"]]).hexdigest() != record["sha256"]:
            raise ValueError("HISTORICAL_PREFIX_CHANGED")
    for name, digest in files.items():
        if hashlib.sha256((old / name).read_bytes()).hexdigest() != digest:
            raise ValueError("ORIGINAL_PREDECESSOR_CHANGED")
    receipt = {"schema": "molecular-continuation.v1", "dataClass": "INTERNAL_PSEUDONYMIZED",
        "recordedAt": datetime.now(timezone.utc).isoformat(), "runtime": "2.1.2",
        "latestHash": before["latest_hash"], "ledgerCount": before["ledger_count"],
        "originalFilesUnchanged": len(files), "exactPrefixes": prefixes,
        "labHistory": {"files": len(history), "checkpointCount": sum(p.parts[0] == "molecular-receipts" for p in history)},
        "cacheMigration": migration, "candidateVerification": after,
        "claimCeiling": "LOCAL_EXACT_PREFIX_CONTINUATION_NOT_EMPIRICAL_BIOLOGY"}
    (new / "PREDECESSOR.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "priorLedgerCount": before["ledger_count"], "priorHead": before["latest_hash"],
        "originalFilesUnchanged": len(files), "newRuntime": "2.1.2", "verify": after["ok"]}))


if __name__ == "__main__":
    main()
