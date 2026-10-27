"""Fork an explicitly selected local NOVA workspace and prove exact ledger prefixes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "src"))
from halveth_nova.workbench.controller import Workbench


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
    files = {str(p.relative_to(old / ".nova")).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (old / ".nova").rglob("*") if p.is_file() and p.name != "write.lock"}
    new.mkdir(parents=True)
    shutil.copytree(old / ".nova", new / ".nova", ignore=shutil.ignore_patterns("write.lock"))
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
    for name, record in prefixes.items():
        if hashlib.sha256((new / ".nova" / name).read_bytes()[:record["bytes"]]).hexdigest() != record["sha256"]:
            raise ValueError("HISTORICAL_PREFIX_CHANGED")
    for name, digest in files.items():
        if hashlib.sha256((old / ".nova" / name).read_bytes()).hexdigest() != digest:
            raise ValueError("ORIGINAL_PREDECESSOR_CHANGED")
    receipt = {"schema": "molecular-continuation.v1", "dataClass": "INTERNAL_PSEUDONYMIZED",
        "recordedAt": datetime.now(timezone.utc).isoformat(), "runtime": "2.1.2",
        "latestHash": before["latest_hash"], "ledgerCount": before["ledger_count"],
        "originalFilesUnchanged": len(files), "exactPrefixes": prefixes,
        "cacheMigration": migration, "candidateVerification": after,
        "claimCeiling": "LOCAL_EXACT_PREFIX_CONTINUATION_NOT_EMPIRICAL_BIOLOGY"}
    (new / "PREDECESSOR.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "priorLedgerCount": before["ledger_count"], "priorHead": before["latest_hash"],
        "originalFilesUnchanged": len(files), "newRuntime": "2.1.2", "verify": after["ok"]}))


if __name__ == "__main__":
    main()
