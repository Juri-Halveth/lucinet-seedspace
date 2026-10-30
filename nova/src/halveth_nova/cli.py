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

    s = sub.add_parser("index", help="compile bounded source adapters, optionally with a local model")
    s.add_argument("paths", nargs="+"); s.add_argument("--limit", type=int, default=500)
    s.add_argument("--local-model")

    s = sub.add_parser("work", help="execute FLOW / ATLAS / DEEP / BUILD controllers")
    s.add_argument("query"); s.add_argument("--mode", choices=sorted(RUN_MODES), default="FLOW")
    s.add_argument("--pattern", help="declared concept-graph query JSON")
    s.add_argument("--local-model", help="explicit model on the fixed local Ollama endpoint")
    s.add_argument("--max-sources", type=int, default=500)
    s.add_argument("--integration", choices=["lagefaden"])
    s.add_argument("--node", default="node", help="explicit local Node executable for the registered integration")
    s.add_argument("--build-spec", help="explicit pure JSON-function build specification and withheld cases")
    s.add_argument("--essence-source", help="source ID of an ingested essence request; association cues also open a research plan")

    s = sub.add_parser("essence-farm", help="expand an explicit source-card request, countertest abstractions and bind new seeds")
    s.add_argument("spec")
    s.add_argument("--mode", choices=["ATLAS", "DEEP", "BUILD"], default="BUILD")
    s.add_argument("--local-model", help="explicit installed model to propose additional source-quoted readings")

    s = sub.add_parser("capabilities", help="show actually available adapters and local model inventory")

    s = sub.add_parser("apply-function", help="explicitly evaluate a generated pure function on a JSON input in the restricted child")
    s.add_argument("code"); s.add_argument("--input", required=True)

    s = sub.add_parser("value-flow", help="bind a value inquiry, measurement gaps and an optional declared cost scenario")
    s.add_argument("spec")

    s = sub.add_parser("bounty-impact", help="sharpen a declared finding into scope, reproduction, impact, root-cause and duplicate gates")
    s.add_argument("spec")

    s = sub.add_parser("transcribe", help="derive a transcript with an existing offline speech model directory")
    s.add_argument("path"); s.add_argument("--model-directory", required=True); s.add_argument("--language")
    s.add_argument("--seconds", type=int, default=30)

    s = sub.add_parser("describe", help="derive visible image content with an explicitly selected local vision model")
    s.add_argument("path"); s.add_argument("--vision-model", required=True)

    s = sub.add_parser("demo", help="execute all four controllers on three synthetic domains")
    s.add_argument("--local-model"); s.add_argument("--node")
    s.add_argument("--generate-function", action="store_true", help="enable the pure-function generator and withheld cases")

    s = sub.add_parser("universe", help="explicit bounded GitHub GET-only adapter")
    s.add_argument("--owner", required=True); s.add_argument("--repo"); s.add_argument("--ref")
    s.add_argument("--max-files", type=int, default=24); s.add_argument("--max-repos", type=int, default=100)

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
            from .workbench.controller import Workbench
            result = Workbench(args.workspace).verify(); emit(result); return 0 if result["ok"] else 2
        elif args.command == "export":
            from .workbench.controller import Workbench
            if not Workbench(args.workspace).verify()["ok"]:
                raise ValueError("WORKBENCH_VERIFICATION_FAILED_BEFORE_EXPORT")
            emit(store.export_zip(args.target))
        elif args.command == "index":
            from .workbench.controller import Workbench
            emit(Workbench(args.workspace).index(args.paths, limit=args.limit, model=args.local_model))
        elif args.command == "work":
            from .workbench.controller import Workbench
            from .jsonutil import strict_loads
            pattern = strict_loads(Path(args.pattern).read_text(encoding="utf-8")) if args.pattern else None
            build_spec = strict_loads(Path(args.build_spec).read_text(encoding="utf-8")) if args.build_spec else None
            emit(Workbench(args.workspace).run(args.query, mode=args.mode, pattern=pattern,
                                              model=args.local_model, max_sources=args.max_sources,
                                              integration=args.integration, node=args.node, build_spec=build_spec,
                                              essence_source=args.essence_source))
        elif args.command == "essence-farm":
            from .workbench.essence import validate_request, expand_with_local_model
            from .workbench.controller import Workbench
            from .jsonutil import strict_loads, canonical_json
            file = Path(args.spec).resolve()
            if file.stat().st_size > 1_000_000:
                raise ValueError("ESSENCE_INPUT_LIMIT")
            with file.open("rb") as stream:
                raw = stream.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("ESSENCE_INPUT_LIMIT")
            request = validate_request(strict_loads(raw.decode("utf-8")))
            source = store.ingest_bytes(store._locator_for(file, file), raw, tags=["essence-input"])
            if args.local_model:
                compiled = expand_with_local_model(request, model=args.local_model)
                receipt = store.ingest_bytes("derived/" + source["source_id"] + "/essence-compiler.json",
                    (canonical_json(compiled["compiler"]) + "\n").encode("utf-8"), tags=["essence-compiler"],
                    metadata={"parent_source_id": source["source_id"], "parent_digest": source["digest"], "state": "MODEL_INFERRED"})
                if compiled["request"] is None:
                    store.set_status(receipt["source_id"], "historical", note="rejected model derivation; exact response retained")
                    emit({"state": "REJECTED_MODEL_DERIVATION", "record": receipt,
                          "reason": compiled["compiler"]["rejection"]})
                    return 2
                source = store.ingest_bytes("derived/" + source["source_id"] + "/essence-expanded.json",
                    (canonical_json(compiled["request"]) + "\n").encode("utf-8"), tags=["essence-input"],
                    metadata={"parent_source_id": source["source_id"], "parent_digest": source["digest"],
                              "compiler_source_id": receipt["source_id"], "state": "MODEL_INFERRED"})
            emit(Workbench(args.workspace).run(request["seed"]["text"], mode=args.mode,
                                               essence_source=source["source_id"]))
        elif args.command == "capabilities":
            from .workbench.adapters import capabilities
            from .workbench.local_model import available_models
            result = capabilities()
            try:
                result["local_models"] = available_models()
            except (OSError, ValueError):
                result["local_models"] = []
            emit(result)
        elif args.command == "apply-function":
            from .workbench.codegen import evaluate
            from .jsonutil import strict_loads, sha256_bytes
            code_file, input_file = Path(args.code), Path(args.input)
            if code_file.stat().st_size > 12000 or input_file.stat().st_size > 400000:
                raise ValueError("PURE_INPUT_LIMIT")
            raw_code, raw_input = code_file.read_bytes(), input_file.read_bytes()
            outcome = evaluate(raw_code.decode("utf-8"), [{"id": "application", "input": strict_loads(raw_input.decode("utf-8")), "expected": None}])
            if "outcomes" not in outcome:
                emit(outcome); return 2
            emit({"contract": "nova.pure-function-application.v1", "state": "OUTPUT_COMPUTED",
                  "source_digest": sha256_bytes(raw_code), "input_digest": sha256_bytes(raw_input),
                  "output": outcome["outcomes"][0]["actual"], "limits": outcome["limits"],
                  "meaning": "computed output; this application supplied no expected-result oracle"})
        elif args.command == "value-flow":
            from .workbench.value_flow import assess
            from .jsonutil import strict_loads, canonical_json
            file = Path(args.spec).resolve()
            if file.stat().st_size > 100000:
                raise ValueError("VALUE_INPUT_LIMIT")
            raw = file.read_bytes(); result = assess(strict_loads(raw.decode("utf-8")))
            source = store.ingest_bytes(store._locator_for(file, file), raw, tags=["value-flow-input"])
            record = store.ingest_bytes("derived/" + source["source_id"] + "/value-flow.json",
                (canonical_json(result) + "\n").encode("utf-8"), tags=["value-flow-result"],
                metadata={"parent_source_id": source["source_id"], "parent_digest": source["digest"], "state": "DECLARED_SCENARIO"})
            emit({"result": result, "record": record})
        elif args.command == "bounty-impact":
            from .workbench.bounty_impact import assess
            from .jsonutil import strict_loads, canonical_json
            file = Path(args.spec).resolve()
            if file.stat().st_size > 100000:
                raise ValueError("BOUNTY_INPUT_LIMIT")
            raw = file.read_bytes(); spec = strict_loads(raw.decode("utf-8"))
            source = store.ingest_bytes(store._locator_for(file, file), raw, tags=["bounty-impact-input"])
            from .workbench.controller import Workbench
            evidence_workbench = Workbench(args.workspace)
            with store.write_lock():
                evidence_sources = {row["source_id"]: row for row in store.sources()}
                evidence_statuses = store.status_map()
                verified_evidence = set()
                for ref in spec.get("evidence_refs", []):
                    try:
                        stored = store.source_by_id(ref.get("id", ""))
                    except KeyError:
                        continue
                    if stored.get("digest") == ref.get("digest"):
                        if evidence_workbench.effective_status(stored["source_id"], evidence_statuses, evidence_sources) != "active":
                            continue
                        try:
                            evidence_workbench.read_object(stored)
                        except (OSError, ValueError):
                            continue
                        verified_evidence.add((ref["id"], ref["digest"]))
                result = assess(spec, verified_evidence=verified_evidence)
                record, created = store._record_source("derived/" + source["source_id"] + "/bounty-impact.json",
                    (canonical_json(result) + "\n").encode("utf-8"), ["bounty-impact-assessment"],
                    {"parent_source_id": source["source_id"], "parent_digest": source["digest"], "state": result["state"]})
                record = {**record, "created": created}
            emit({"result": result, "record": record})
        elif args.command == "universe":
            from .workbench.github_adapter import inventory
            emit(inventory(store, args.owner, repo=args.repo, ref=args.ref, max_files=args.max_files, max_repos=args.max_repos))
        elif args.command == "transcribe":
            from .workbench.media import transcribe
            from .jsonutil import canonical_json
            file = Path(args.path).resolve()
            if file.stat().st_size > 8_000_000:
                raise ValueError("MEDIA_INPUT_LIMIT")
            raw = file.read_bytes()
            source = store.ingest_bytes(store._locator_for(file, file), raw, tags=["speech-input"])
            result = transcribe(raw, Path(args.model_directory), language=args.language, seconds_limit=args.seconds)
            result["parent_source_id"] = source["source_id"]
            record = store.ingest_bytes("derived/" + source["source_id"] + "/transcript.json",
                (canonical_json(result) + "\n").encode("utf-8"), tags=["speech-transcript"],
                metadata={"parent_source_id": source["source_id"], "parent_digest": source["digest"], "state": "MODEL_INFERRED"})
            emit({"result": result, "record": record})
        elif args.command == "describe":
            from .workbench.vision import describe
            from .workbench.adapters import extract
            from .jsonutil import canonical_json
            file = Path(args.path).resolve()
            if file.stat().st_size > 8_000_000:
                raise ValueError("VISION_IMAGE_LIMIT")
            raw = file.read_bytes()
            pixels = extract(file.name, raw)
            if pixels["adapter"] != "image-pixels" or not pixels["facts"].get("width"):
                raise ValueError("DECODED_IMAGE_REQUIRED")
            source = store.ingest_bytes(store._locator_for(file, file), raw, tags=["vision-input"])
            result = describe(raw, model=args.vision_model); result["parent_source_id"] = source["source_id"]
            record = store.ingest_bytes("derived/" + source["source_id"] + "/vision.json",
                (canonical_json(result) + "\n").encode("utf-8"), tags=["vision-derivation"],
                metadata={"parent_source_id": source["source_id"], "parent_digest": source["digest"], "state": "MODEL_INFERRED"})
            emit({"result": result, "record": record})
        elif args.command == "demo":
            from .workbench.demo import run
            result = run(args.workspace, model=args.local_model, node=args.node, generate_function=args.generate_function)
            emit(result)
            return 0 if result["outcome"] == "DEMO_PASSED" and result["verification"]["ok"] else 2
        else:
            raise RuntimeError("unknown command")
        return 0
    except Exception as e:
        print(f"NOVA_ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
