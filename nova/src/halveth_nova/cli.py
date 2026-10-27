from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine import NovaEngine
from .model import CLAIM_STATES, RELATION_STATES, RELATION_TYPES, RUN_MODES, SOURCE_STATUSES, Claim
from .store import NovaStore


def emit(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nova", description="HALVETH NOVA provenance-preserving research continuity runtime")
    p.add_argument("--version", action="version", version=f"halveth-nova {__version__}")
    p.add_argument("--workspace", default=".", help="workspace directory (default: current directory)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="initialize .nova workspace")
    s.add_argument("--name")

    s = sub.add_parser("ingest", help="ingest file or directory as exact source bytes")
    s.add_argument("path"); s.add_argument("--tag", action="append", default=[]); s.add_argument("--max-bytes", type=int, default=8_000_000)
    s.add_argument("--meta", action="append", default=[], help="metadata key=value")

    s = sub.add_parser("search", help="search sources without executing them")
    s.add_argument("query"); s.add_argument("--limit", type=int, default=20); s.add_argument("--exclude-retracted", action="store_true")

    s = sub.add_parser("source-status", help="append source status event")
    s.add_argument("source_id"); s.add_argument("status", choices=sorted(SOURCE_STATUSES)); s.add_argument("--note", default=""); s.add_argument("--superseded-by")

    s = sub.add_parser("relate", help="append typed relation")
    s.add_argument("subject"); s.add_argument("predicate", choices=sorted(RELATION_TYPES)); s.add_argument("object"); s.add_argument("--state", choices=sorted(RELATION_STATES), default="hypothesis"); s.add_argument("--evidence", action="append", default=[]); s.add_argument("--note", default="")

    s = sub.add_parser("run", help="search + append research receipt + update resume seed")
    s.add_argument("query"); s.add_argument("--mode", choices=sorted(RUN_MODES), default="FLOW"); s.add_argument("--limit", type=int, default=10)
    s.add_argument("--claim", action="append", default=[], help="STATE:text, e.g. HYPOTHESIS:possible bridge")
    s.add_argument("--claim-evidence", action="append", default=[], help="source id attached to every --claim")
    s.add_argument("--open", action="append", default=[]); s.add_argument("--artifact", action="append", default=[]); s.add_argument("--next-seed", default=""); s.add_argument("--note", default="")
    s.add_argument("--expect-prev-hash", default=None)

    s = sub.add_parser("resume", help="show verified latest continuation state")

    s = sub.add_parser("status", help="show workspace counts and current source statuses")

    s = sub.add_parser("verify", help="verify source objects, ledger hash chain and resume")

    s = sub.add_parser("export", help="export verified .nova state as reproducible zip")
    s.add_argument("target")

    return p


def parse_meta(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"metadata must be key=value: {item}")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError("metadata key cannot be empty")
        out[key] = value
    return out


def parse_claims(items: list[str], evidence: list[str]) -> list[Claim]:
    out: list[Claim] = []
    for item in items:
        if ":" not in item:
            raise ValueError("claim must be STATE:text")
        state, text = item.split(":", 1)
        state = state.strip().upper()
        if state not in CLAIM_STATES:
            raise ValueError(f"invalid claim state: {state}")
        if not text.strip():
            raise ValueError("claim text cannot be empty")
        out.append(Claim(text.strip(), state, list(evidence)))
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = NovaEngine(args.workspace)
    store = engine.store
    try:
        if args.command == "init":
            emit(engine.init(args.name))
        elif args.command == "ingest":
            emit(engine.ingest(args.path, tags=args.tag, metadata=parse_meta(args.meta), max_bytes=args.max_bytes))
        elif args.command == "search":
            emit(engine.search(args.query, limit=args.limit, include_retracted=not args.exclude_retracted))
        elif args.command == "source-status":
            emit(store.set_status(args.source_id, args.status, note=args.note, superseded_by=args.superseded_by))
        elif args.command == "relate":
            emit(store.add_relation(args.subject, args.predicate, args.object, args.state, args.evidence, args.note))
        elif args.command == "run":
            emit(engine.run(args.query, mode=args.mode, limit=args.limit, claims=parse_claims(args.claim, args.claim_evidence), open_questions=args.open, artifacts=args.artifact, next_seed=args.next_seed, note=args.note, expected_previous_hash=args.expect_prev_hash))
        elif args.command == "resume":
            emit(engine.resume())
        elif args.command == "status":
            store.require()
            emit({"config": store.read_config(), "verification": store.verify(), "source_status": store.status_map()})
        elif args.command == "verify":
            result = store.verify(); emit(result); return 0 if result["ok"] else 2
        elif args.command == "export":
            emit(store.export_zip(args.target))
        else:
            raise RuntimeError("unknown command")
        return 0
    except Exception as e:
        print(f"NOVA_ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
