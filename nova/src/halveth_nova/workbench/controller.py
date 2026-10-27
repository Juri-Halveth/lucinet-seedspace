from __future__ import annotations

import json
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

from ..engine import NovaEngine, RECEIPT_CONTRACT
from ..jsonutil import canonical_json, sha256_bytes, sha256_json, strict_loads
from ..search import score_candidate
from ..store import atomic_write, utc_now
from . import WORKBENCH_VERSION
from .adapters import ADAPTER_BUNDLE_VERSION, MAX_BYTES, capabilities, extract
from .graph import addressed_relations, structural_match, unknown_key, validate_graph

CONTRACT = "nova.workbench-result.v1"
SKIP_PARTS = {".git", ".nova", ".venv", "node_modules", "__pycache__", "target"}
SECRET = re.compile(r"(^|[_.-])(env|secrets?|credentials?|cookies?|tokens?|private[-_]key)([_.-]|$)", re.I)


class Workbench:
    def __init__(self, workspace: str | Path):
        self.engine = NovaEngine(workspace)
        self.store = self.engine.store
        self.home = self.store.nova / "workbench"

    def source_state(self) -> str:
        return sha256_json({"sources": self.store.sources(), "events": self.store.source_events()})

    def effective_status(self, source_id: str, statuses: dict, sources: dict | None = None) -> str:
        sources = sources if sources is not None else {s["source_id"]: s for s in self.store.sources()}
        current, seen = source_id, set()
        own = statuses[current]["status"]
        while current:
            if current in seen or current not in sources:
                raise ValueError("DERIVATION_PARENT_CYCLE_OR_MISSING")
            seen.add(current)
            if statuses[current]["status"] != "active":
                return statuses[current]["status"]
            metadata = sources[current].get("metadata", {})
            parent = metadata.get("parent_source_id")
            if parent:
                if parent not in sources or metadata.get("parent_digest") != sources[parent]["digest"]:
                    raise ValueError("DERIVATION_PARENT_BINDING_CHANGED")
            current = parent
        return own

    def read_object(self, source: dict) -> bytes:
        if not re.fullmatch(r"src_[a-f0-9]{20}", source.get("source_id", "")) or not re.fullmatch(r"[a-f0-9]{64}", source.get("digest", "")):
            raise ValueError("INVALID_SOURCE_ADDRESS")
        data = (self.store.objects / source["digest"]).read_bytes()
        if len(data) != source["byte_length"] or sha256_bytes(data) != source["digest"]:
            raise ValueError("SOURCE_OBJECT_CHANGED")
        return data

    def _history_refs(self, source_id: str) -> list[dict]:
        folder = self.home / "analysis-history"
        refs = []
        if not folder.exists():
            return refs
        for path in sorted(folder.glob("*.json")):
            raw = path.read_bytes()
            prior = strict_loads(raw.decode("utf-8"))
            check = dict(prior); digest = check.pop("analysis_digest", None)
            if digest != path.stem or sha256_json(check) != digest:
                raise ValueError("HISTORICAL_ANALYSIS_BINDING_CHANGED")
            if prior.get("source_id") == source_id:
                refs.append({"path": path.name, "sha256": sha256_bytes(raw), "bytes": len(raw)})
        return refs

    def _verify_history_refs(self, refs: list[dict]) -> None:
        folder = (self.home / "analysis-history").resolve()
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "bytes"}:
                raise ValueError("HISTORICAL_ANALYSIS_REFERENCE_INVALID")
            path = (folder / ref["path"]).resolve()
            if not path.is_relative_to(folder) or path.name != ref["path"]:
                raise ValueError("HISTORICAL_ANALYSIS_REFERENCE_INVALID")
            if not path.is_file():
                raise ValueError("HISTORICAL_ANALYSIS_MISSING")
            raw = path.read_bytes()
            if len(raw) != ref["bytes"] or sha256_bytes(raw) != ref["sha256"]:
                raise ValueError("HISTORICAL_ANALYSIS_BYTES_CHANGED")

    def index(self, paths: list[str | Path], *, limit: int = 500, model: str | None = None) -> dict:
        self.store.require()
        if not 1 <= limit <= 10000:
            raise ValueError("INVALID_INDEX_LIMIT")
        admitted, held, visited = [], [], 0
        for path in paths:
            root = Path(path).resolve()
            if not root.exists():
                raise FileNotFoundError(root)
            def walk_files():
                for directory, dirs, names in os.walk(root, followlinks=False):
                    for name in sorted(dirs):
                        folder = Path(directory) / name
                        if name in SKIP_PARTS or folder.is_symlink():
                            held.append({"locator": self.store._locator_for(folder, root),
                                         "reason": "EXCLUDED_LOCAL_STATE_OR_SECRET_NAME"})
                    dirs[:] = sorted(d for d in dirs if d not in SKIP_PARTS and not (Path(directory) / d).is_symlink())
                    for name in sorted(names):
                        yield Path(directory) / name
            files = walk_files() if root.is_dir() else [root]
            for file in files:
                if not file.is_file():
                    continue
                rel_parts = file.relative_to(root).parts if root.is_dir() else (file.name,)
                locator = self.store._locator_for(file, root)
                reason = None
                if file.is_symlink() or not file.resolve().is_relative_to(root if root.is_dir() else root.parent):
                    reason = "SYMLINK_OR_OUTSIDE_ROOT"
                elif SKIP_PARTS.intersection(rel_parts) or SECRET.search(file.name):
                    reason = "EXCLUDED_LOCAL_STATE_OR_SECRET_NAME"
                elif visited >= limit:
                    reason = "FILE_BUDGET"
                elif file.stat().st_size > MAX_BYTES:
                    reason = "MAX_BYTES"
                if reason:
                    held.append({"locator": locator, "reason": reason})
                    if reason == "FILE_BUDGET":
                        break  # finite traversal; omitted tail is not enumerated or claimed complete
                    continue
                visited += 1
                with file.open("rb") as stream:
                    data = stream.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    held.append({"locator": locator, "reason": "MAX_BYTES_AFTER_READ"})
                    continue
                rec = self.store.ingest_bytes(locator, data, tags=["workbench-input"], metadata={"data_class": "INTERNAL_PSEUDONYMIZED"})
                admitted.append(rec["source_id"])
        compilation = self.compile_sources(model=model)
        return {"contract": "nova.index-receipt.v1", "admitted": admitted, "held": held,
                "files_read": visited, "file_budget": limit, "coverage": "FINITE_EXPLICIT_ROOTS",
                "unvisited_tail": "UNKNOWN" if any(h["reason"] == "FILE_BUDGET" for h in held) else "ENUMERATED_WITH_EXCLUSIONS",
                **compilation}

    def compile_sources(self, *, model: str | None = None) -> dict:
        self.store.require()
        count, failures = 0, []
        for source in self.store.sources():
            if "workbench-result" in source.get("tags", []):
                continue
            data = self.read_object(source)
            path = self.home / "analyses" / (source["source_id"] + ".json")
            cached = None
            if path.exists():
                cached = strict_loads(path.read_text(encoding="utf-8"))
                check = dict(cached); digest = check.pop("analysis_digest", None)
                if sha256_json(check) != digest or cached["parent_digest"] != source["digest"]:
                    raise ValueError("ANALYSIS_BINDING_CHANGED")
                if "history_refs" in cached:
                    self._verify_history_refs(cached["history_refs"])
                else:
                    # One-time migration for pre-2.0.2 caches. Preserve the exact legacy
                    # current-cache bytes first, then bind all retained archives from the
                    # migrated record so the migration itself does not erase history.
                    legacy_bytes = path.read_bytes()
                    historical = self.home / "analysis-history" / (cached["analysis_digest"] + ".json")
                    if historical.exists() and historical.read_bytes() != legacy_bytes:
                        raise ValueError("HISTORICAL_ANALYSIS_BYTES_CHANGED")
                    if not historical.exists():
                        atomic_write(historical, legacy_bytes)
                    cached["history_refs"] = self._history_refs(source["source_id"])
                    cached.pop("analysis_digest", None)
                    cached["analysis_digest"] = sha256_json(cached)
                    atomic_write(path, (canonical_json(cached) + "\n").encode("utf-8"))
                compilation = cached["analysis"].get("model_compilation")
                if cached.get("adapter_bundle_version") == ADAPTER_BUNDLE_VERSION and (model is None or (compilation and compilation.get("model") == model)):
                    count += 1
                    continue
            try:
                result = extract(source["locator"], data)
            except (ValueError, SyntaxError, OSError, RuntimeError, zipfile.BadZipFile) as error:
                result = {"contract": "nova.adapter-result.v1", "adapter_version": "1.0.0",
                          "adapter": "FAILED", "parent_digest": source["digest"], "text": "", "graphs": [],
                          "facts": {}, "coverage": {"input_bytes": len(data)}, "gaps": [type(error).__name__]}
                failures.append({"source_id": source["source_id"], "reason": type(error).__name__})
            if model and result.get("text") and not result.get("graphs"):
                from .local_model import compile_concepts
                try:
                    result["model_compilation"] = compile_concepts(result["text"][:12000], model=model)
                    if len(result["text"]) > 12000:
                        result["gaps"].append("MODEL_SOURCE_PREFIX_12000_CHARS")
                except (ValueError, KeyError, OSError, RuntimeError) as error:
                    result["gaps"].append("MODEL_COMPILATION_REJECTED:" + type(error).__name__)
            history_refs = []
            if cached:
                # Cache upgrades preserve the exact previous derivation, including model bindings.
                history_refs = list(cached.get("history_refs", []))
                historical = self.home / "analysis-history" / (cached["analysis_digest"] + ".json")
                previous_bytes = path.read_bytes()
                if historical.exists() and historical.read_bytes() != previous_bytes:
                    raise ValueError("HISTORICAL_ANALYSIS_BYTES_CHANGED")
                if not historical.exists():
                    atomic_write(historical, previous_bytes)
                ref = {"path": historical.name, "sha256": sha256_bytes(previous_bytes), "bytes": len(previous_bytes)}
                if ref not in history_refs:
                    history_refs.append(ref)
                old_compilation = cached["analysis"].get("model_compilation")
                if model is None and old_compilation and cached["analysis"].get("text") == result.get("text"):
                    result["model_compilation"] = old_compilation
            row = {"source_id": source["source_id"], "parent_digest": source["digest"], "analysis": result,
                   "adapter_bundle_version": ADAPTER_BUNDLE_VERSION, "history_refs": history_refs}
            row["analysis_digest"] = sha256_json(row)
            atomic_write(self.home / "analyses" / (source["source_id"] + ".json"), (canonical_json(row) + "\n").encode("utf-8"))
            count += 1
        return {"sources_compiled": count, "adapter_failures": failures}

    def analyses(self) -> list[dict]:
        rows = []
        for source in self.store.sources():
            if "workbench-result" in source.get("tags", []):
                continue
            path = self.home / "analyses" / (source["source_id"] + ".json")
            if not path.exists():
                continue
            row = strict_loads(path.read_text(encoding="utf-8"))
            check = dict(row); got = check.pop("analysis_digest", None)
            if row.get("parent_digest") != source["digest"] or sha256_json(check) != got:
                raise ValueError("ANALYSIS_BINDING_CHANGED")
            self._verify_history_refs(row.get("history_refs", []))
            self.read_object(source)
            rows.append({**row, "source": source})
        return rows

    def retrieve(self, query: str, rows: list[dict], *, limit: int = 20) -> list[dict]:
        statuses = self.store.status_map()
        source_map = {s["source_id"]: s for s in self.store.sources()}
        hits = []
        for row in rows:
            source = row["source"]
            status = self.effective_status(source["source_id"], statuses, source_map)
            analysis = row["analysis"]
            text = analysis.get("text", "")
            aliases = [a for g in analysis.get("graphs", []) for n in g["nodes"] for a in n.get("aliases", [])]
            for alias in (analysis.get("model_compilation") or {}).get("aliases", []):
                aliases.extend([alias["term"], alias["alias"]])
            searchable = source["locator"] + "\n" + text + "\n" + " ".join(aliases)
            score = score_candidate(query, searchable, status)
            if score <= 0:
                continue
            lines = text.splitlines() or [""]
            terms = re.findall(r"\w+", query.casefold())
            at = next((i for i, line in enumerate(lines) if any(t in line.casefold() for t in terms)), 0)
            start, end = max(0, at - 1), min(len(lines), at + 3)
            hits.append({"source_id": source["source_id"], "digest": source["digest"], "locator": source["locator"],
                         "status": status, "usable_as_current": status == "active", "score": score,
                         "representation": analysis["adapter"], "line_start": start + 1, "line_end": end,
                         "span_layer": "DERIVED_TEXT" if analysis["adapter"] != "utf8-text" else "SOURCE_TEXT",
                         "analysis_digest": row["analysis_digest"], "excerpt": "\n".join(lines[start:end])[:1800]})
        hits.sort(key=lambda h: (-h["score"], h["locator"], h["source_id"]))
        return hits[:limit]

    def prior_results(self) -> list[dict]:
        sources = {s["source_id"]: s for s in self.store.sources()}
        results = []
        for entry in self.store.ledger():
            descriptor = entry["receipt"].get("controller", {})
            source = sources.get(descriptor.get("artifact_source_id"))
            if source is None:
                continue
            data = self.read_object(source)
            if source["digest"] != descriptor.get("artifact_digest"):
                raise ValueError("CONTROLLER_ARTIFACT_BINDING_CHANGED")
            results.append(strict_loads(data.decode("utf-8")))
        return results

    def run(self, query: str, *, mode: str = "FLOW", pattern: dict | None = None,
            model: str | None = None, max_sources: int = 500, integration: str | None = None,
            node: str = "node", build_spec: dict | None = None, essence_source: str | None = None) -> dict:
        self.store.require()
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError("INVALID_TASK")
        if mode not in {"FLOW", "ATLAS", "DEEP", "BUILD"}:
            raise ValueError("INVALID_CONTROLLER_MODE")
        if build_spec is not None and (mode != "BUILD" or not model):
            raise ValueError("PURE_BUILD_REQUIRES_BUILD_MODE_AND_LOCAL_MODEL")
        if pattern is not None:
            validate_graph(pattern)
            if len(pattern["nodes"]) > 8:
                raise ValueError("PATTERN_NODE_LIMIT_8")
        verification = self.store.verify()
        if not verification["ok"]:
            raise RuntimeError("INVALID_WORKSPACE")
        latest = self.store.latest_ledger()
        previous = latest["entry_hash"] if latest else None
        self.compile_sources()
        source_state = self.source_state()
        rows = self.analyses()
        if not 1 <= max_sources <= 10000 or len(rows) > max_sources:
            raise ValueError("SOURCE_BUDGET_EXCEEDED: select a bounded workspace")
        run_id = "work_" + uuid.uuid4().hex
        statuses = self.store.status_map()
        source_map = {s["source_id"]: s for s in self.store.sources()}
        hits = self.retrieve(query, rows, limit=3 if mode == "FLOW" else 50)
        result = {"contract": CONTRACT, "controller_version": WORKBENCH_VERSION, "run_id": run_id,
                  "task": query, "mode": mode, "created_at": utc_now(), "input_state_digest": source_state,
                  "stages": ["compile_adapters", "retrieve"], "hits": hits, "graphs": [], "structural_matches": [],
                  "unknowns": [], "coverage": {"indexed_sources": len(rows), "raw_sources": len(self.store.sources()),
                                              "capabilities": capabilities()},
                  "model_compilation": None, "countertests": [], "build": None,
                  "inferred_graphs": [], "inferred_structural_matches": [], "recovered_runs": [], "relation_records": [],
                  "authority": "LOCAL_DERIVATION_ONLY", "action_requests": [], "artifacts": []}
        from .essence import detect_association, harvest, plan
        cue = detect_association(query)
        result["association_cue"] = cue
        result["essence_farms"] = []
        requests = [row for row in rows if row["analysis"].get("essence_request") and
                    self.effective_status(row["source_id"], statuses, source_map) == "active"]
        if essence_source:
            requests = [row for row in requests if row["source_id"] == essence_source]
            if not requests:
                raise ValueError("ACTIVE_ESSENCE_SOURCE_REQUIRED")
        elif cue["state"] == "LEXICAL_CUE_FOUND":
            terms = set(re.findall(r"\w+", query.casefold()))
            requests = [row for row in requests if terms.intersection(re.findall(
                r"\w+", row["analysis"]["essence_request"]["seed"]["text"].casefold()))]
        else:
            requests = []
        for row in requests:
            farm = harvest(row["analysis"]["essence_request"],
                request_ref={"source_id": row["source_id"], "digest": row["parent_digest"]}, recorded_at=result["created_at"])
            farm["producer_state"] = row["source"].get("metadata", {}).get("state", "SUPPLIED_READING")
            result["essence_farms"].append(farm)
        if not requests and cue["state"] == "LEXICAL_CUE_FOUND":
            result["essence_farms"].append(plan(query, recorded_at=result["created_at"]))
        if result["essence_farms"]:
            result["stages"].append("association_expand_compare_distill")
            for farm in result["essence_farms"]:
                result["unknowns"].extend(dict(question) for question in farm["new_seeds"])
            result["countertests"].extend({"operator": "reverse_declared_essence_transition",
                "candidate_id": c["id"], "results": c["countertests"], "meaning": "declared roles, not a physical test"}
                for farm in result["essence_farms"] for c in farm["candidate_essences"])
        if model:
            from .local_model import compile_concepts
            if pattern is None:
                try:
                    task_graph = compile_concepts(query, model=model, task="Extract only the requested structural query pattern.")
                    result["task_interpretation"] = {**task_graph, "input_kind": "USER_TASK_NOT_OBSERVATION"}
                    candidate_pattern = task_graph.get("graph")
                    if candidate_pattern is not None and len(candidate_pattern["nodes"]) > 8:
                        result["coverage"]["task_interpretation"] = {
                            "state": "OPEN", "reason": "PATTERN_NODE_LIMIT_8",
                            "nodes": len(candidate_pattern["nodes"])
                        }
                    else:
                        pattern = candidate_pattern
                except (ValueError, KeyError, OSError, RuntimeError) as error:
                    result["coverage"]["task_interpretation"] = {"state": "OPEN", "reason": type(error).__name__}
            selected = [h for h in hits if h["usable_as_current"]][:3]
            text = "\n\n".join(h["excerpt"] for h in selected)
            if not text:
                result["coverage"]["model"] = "NO_ACTIVE_TEXT_INPUT"
            else:
                try:
                    compiled = compile_concepts(text, model=model, task=query)
                    compiled["source_bindings"] = [{k: h[k] for k in ("source_id", "digest", "analysis_digest")} for h in selected]
                    fragments, offset = [], 0
                    for hit in selected:
                        length = len(hit["excerpt"].encode("utf-16-le")) // 2
                        fragments.append({**{k: hit[k] for k in ("source_id", "digest", "analysis_digest", "line_start", "line_end", "span_layer")},
                                          "excerpt_digest": sha256_bytes(hit["excerpt"].encode("utf-8")),
                                          "compiled_input_start_utf16": offset, "compiled_input_end_utf16": offset + length})
                        offset += length + 2  # two newline characters between excerpts
                    compiled["input_fragments"] = fragments
                    result["model_compilation"] = compiled
                    result["stages"].append("local_concept_compiler")
                except (ValueError, KeyError, OSError, RuntimeError) as error:
                    result["coverage"]["model"] = {"state": "MODEL_DERIVATION_REJECTED", "reason": type(error).__name__}
        if mode != "FLOW":
            result["stages"].append("atlas_structure_and_coverage")
            for row in rows:
                if self.effective_status(row["source_id"], statuses, source_map) != "active":
                    continue
                for graph in row["analysis"].get("graphs", []):
                    result["graphs"].append({"source_id": row["source_id"], "source_digest": row["parent_digest"], "graph": graph})
                    result["relation_records"].extend(addressed_relations(graph, source_id=row["source_id"],
                        source_digest=row["parent_digest"], run_id=run_id, recorded_at=result["created_at"],
                        evidence_state="AST_SYNTAX_DERIVED" if row["analysis"]["adapter"] == "python-ast" else "SOURCE_DECLARED"))
                    if pattern is not None:
                        match = structural_match(pattern, graph)
                        result["structural_matches"].append({"source_id": row["source_id"], **match})
                model_graph = (row["analysis"].get("model_compilation") or {}).get("graph")
                if model_graph:
                    result["inferred_graphs"].append({"source_id": row["source_id"], "graph": model_graph,
                                                      "state": "MODEL_INFERRED", "authority": "NONE"})
                    result["relation_records"].extend(addressed_relations(model_graph, source_id=row["source_id"],
                        source_digest=row["parent_digest"], run_id=run_id, recorded_at=result["created_at"], evidence_state="MODEL_INFERRED"))
                    if pattern is not None:
                        result["inferred_structural_matches"].append({"source_id": row["source_id"],
                            "state": "MODEL_INFERRED", **structural_match(pattern, model_graph)})
                for gap in row["analysis"].get("gaps", []):
                    result["unknowns"].append({"field": "adapter_coverage", "referent": row["source_id"],
                                               "scope": row["analysis"]["adapter"], "question": gap,
                                               "resolver": "provide a compatible source adapter or a bound observation"})
                for question in row["analysis"].get("unknowns", []):
                    result["unknowns"].append({**question, "source_refs": [{"source_id": row["source_id"],
                                                                          "digest": row["parent_digest"]}]})
            for item in result["graphs"]:
                result["unknowns"].extend(dict(u) for u in item["graph"].get("unknowns", []))
            prior = self.prior_results()
            for old in prior:
                score = score_candidate(query, old["task"] + "\n" + canonical_json(old.get("model_compilation")) +
                                        "\n" + (old.get("function_build") or {}).get("description", ""), "historical")
                if score > 0:
                    result["recovered_runs"].append({"run_id": old["run_id"], "task": old["task"],
                                                      "score": score, "kind": "DERIVED_PRIOR_WORK"})
            result["recovered_runs"].sort(key=lambda r: (-r["score"], r["run_id"]))
        if result["unknowns"]:
            prior = self.prior_results()
            for unknown in result["unknowns"]:
                key = unknown_key(unknown)
                occurrences = [{"run_id": old["run_id"], "source_state_digest": old["input_state_digest"]}
                               for old in prior if any(u.get("unknown_id") == key for u in old["unknowns"])]
                unknown.update(unknown_id=key, prior_occurrences=occurrences, state="UNKNOWN",
                               reopen_trigger=unknown.get("resolver", "new source with matching referent and scope"))
                family = sha256_json({k: unknown.get(k) for k in ("field", "definition")})[:24]
                unknown["gap_family"] = {"id": "gap_family_" + family, "meaning": "same declared gap class, not same referent",
                    "prior_referents": sorted({u["referent"] for old in prior for u in old["unknowns"]
                        if {k: u.get(k) for k in ("field", "definition")} == {k: unknown.get(k) for k in ("field", "definition")}})}
            facets = sorted({u["field"] for u in result["unknowns"]})
            result["coverage"]["unknown_facets"] = facets
        if mode in {"DEEP", "BUILD"}:
            result["stages"].append("select_unknown_and_countertest")
            result["selected_unknown"] = next(iter(sorted(result["unknowns"],
                key=lambda u: (-score_candidate(query, " ".join(str(u.get(k, "")) for k in ("field", "question", "scope", "resolver")).replace("_", " "), "active"),
                               -len(u["prior_occurrences"]), u["unknown_id"]))), None)
            if pattern is not None:
                reversed_pattern = {**pattern, "edges": [{**e, "from": e["to"], "to": e["from"]} for e in pattern["edges"]]}
                for item in result["graphs"]:
                    reverse = structural_match(reversed_pattern, item["graph"])
                    result["countertests"].append({"source_id": item["source_id"], "operator": "reverse_pattern_edges",
                                                   "result": reverse, "meaning": "structural discriminator, not a causal test"})
            if not result["graphs"]:
                result["action_requests"].append({"kind": "NEEDS_GRAPH_OR_COMPILER", "state": "OPEN",
                                                   "request": "provide a declared graph or a validated model derivation"})
            if integration is not None:
                if integration != "lagefaden":
                    raise ValueError("UNREGISTERED_INTEGRATION")
                from .integrations import lagefaden
                result["stages"].append("execute_bound_lagefaden_replay")
                result["integration"] = lagefaden(node=node)
        elif integration is not None:
            raise ValueError("INTEGRATION_REQUIRES_DEEP_OR_BUILD")
        # Model-derived graph remains in its own lane, never quietly promoted into declared source graphs.
        if mode == "BUILD":
            from .builder import build_kit
            result["stages"].append("build_compile_and_execute_portable_kit")
            result["build"] = build_kit(self.home / "builds" / run_id, result, pattern)
            for key in ("directory", "viewer"):
                result["build"][key] = Path(result["build"][key]).relative_to(self.store.root).as_posix()
            result["artifacts"] = result["build"]["files"]
            if build_spec is not None:
                from .codegen import build_function
                result["stages"].append("generate_pure_function_and_run_withheld_cases")
                result["function_build"] = build_function(self.home / "builds" / run_id / "generated-function", build_spec, model=model)
        result["stages"].append("receipt_and_next_seed")
        result["next_seed"] = {"task": query, "suggested_mode": "DEEP" if result["unknowns"] else "ATLAS",
                               "unknown_ids": sorted({u["unknown_id"] for u in result["unknowns"]}),
                               "selected_unknown_id": (result.get("selected_unknown") or {}).get("unknown_id"),
                               "next_action": (result.get("selected_unknown") or {}).get("resolver"),
                               "essence_request_refs": [f["request_ref"] for f in result["essence_farms"] if f["request_ref"]],
                               "authority_inherited": False}
        with self.store.write_lock():
            if self.source_state() != source_state:
                raise RuntimeError("SOURCE_STATE_CHANGED")
            current = self.store.latest_ledger()
            if (current["entry_hash"] if current else None) != previous:
                raise RuntimeError("STALE_PREDECESSOR")
            generated = result.get("function_build")
            if generated:
                folder = self.home / "builds" / run_id / "generated-function"
                bound = []
                for file in sorted(folder.iterdir()):
                    if not (file.suffix == ".py" or file.name == "SPEC.json"):
                        continue
                    source, _ = self.store._record_source(
                        "generated/" + run_id + "/" + file.name, file.read_bytes(),
                        ["generated-function", "workbench-input"], {"data_class": "INTERNAL_PSEUDONYMIZED",
                            "generator_run_id": run_id, "spec_digest": generated["spec_digest"],
                            "build_state": generated["state"], "description": generated["description"]})
                    # Attempts stay searchable history. Only a passing selected candidate is current code.
                    if file.name != "SPEC.json" and (file.name != "candidate.py" or generated["state"] != "TESTED_CANDIDATE"):
                        self.store._set_status_unlocked(source["source_id"], "historical", note="preserved generation attempt")
                    bound.append({"source_id": source["source_id"], "digest": source["digest"], "file": file.name})
                result["generated_sources"] = bound
            if result["build"]:
                from .builder import finalize_kit
                result["build"] = finalize_kit(self.home / "builds" / run_id, result)
                result["artifacts"] = result["build"]["files"]
            data = (canonical_json(result) + "\n").encode("utf-8")
            record, _ = self.store._record_source("workbench/results/" + run_id + ".json", data,
                                                 ["workbench-result"], {"data_class": "INTERNAL_PSEUDONYMIZED"})
            receipt = {"contract": RECEIPT_CONTRACT, "run_id": run_id, "created_at": result["created_at"],
                       "mode": mode, "query": query, "input_sources": hits, "claims": [],
                       "open_questions": [u["question"] for u in result["unknowns"]],
                       "artifacts": [record["source_id"]], "relations_visible": [],
                       "predecessor_run_id": latest["receipt"]["run_id"] if latest else None,
                       "predecessor_entry_hash": previous, "next_seed": canonical_json(result["next_seed"]),
                       "note": "Work controller executed; see bound result for stages, structure and coverage.",
                       "controller": {"contract": CONTRACT, "version": WORKBENCH_VERSION,
                                      "artifact_source_id": record["source_id"], "artifact_digest": record["digest"]}}
            envelope = self.store._append_receipt_unlocked(receipt, expected_previous_hash=previous)
        return {"result": result, "ledger": {"run_id": run_id, "sequence": envelope["sequence"],
                                             "entry_hash": envelope["entry_hash"], "artifact_source_id": record["source_id"]}}

    def verify(self) -> dict:
        base = self.store.verify()
        try:
            rows = self.analyses(); results = self.prior_results()
            for path in (self.home / "analysis-history").glob("*.json"):
                prior = strict_loads(path.read_text(encoding="utf-8"))
                digest = prior.pop("analysis_digest", None)
                if digest != path.stem or sha256_json(prior) != digest:
                    raise ValueError("HISTORICAL_ANALYSIS_BINDING_CHANGED")
            sources = {s["source_id"]: s for s in self.store.sources()}
            for result in results:
                if result.get("contract") != CONTRACT:
                    raise ValueError("INVALID_RESULT_CONTRACT")
                from .essence import harvest, plan
                for farm in result.get("essence_farms", []):
                    ref = farm.get("request_ref")
                    if ref:
                        source = sources[ref["source_id"]]
                        if source["digest"] != ref["digest"]:
                            raise ValueError("ESSENCE_REQUEST_BINDING_CHANGED")
                        expected = harvest(strict_loads(self.read_object(source).decode("utf-8")), request_ref=ref,
                                           operator_version=farm["operator_version"], recorded_at=result["created_at"])
                        expected["producer_state"] = source.get("metadata", {}).get("state", "SUPPLIED_READING")
                    else:
                        expected = plan(result["task"], operator_version=farm["operator_version"], recorded_at=result["created_at"])
                    if farm != expected:
                        raise ValueError("ESSENCE_DERIVATION_CHANGED")
                expected_relations = []
                for item in result["graphs"] + result.get("inferred_graphs", []):
                    matching = [r for r in result.get("relation_records", []) if
                                r["source_refs"][0]["source_id"] == item["source_id"] and
                                r["left"]["semantic_address"]["graph_digest"] == sha256_json(item["graph"])]
                    if matching:
                        ref = matching[0]
                        expected_relations.extend(addressed_relations(item["graph"], source_id=item["source_id"],
                            source_digest=sources[item["source_id"]]["digest"], run_id=result["run_id"],
                            recorded_at=result["created_at"], evidence_state=ref["evidence_state"]))
                    elif item["graph"]["edges"]:
                        raise ValueError("RELATION_RECORDS_MISSING")
                records = result.get("relation_records", [])
                if len({r["relation_id"] for r in records}) != len(records) or sorted(expected_relations, key=lambda r: r["relation_id"]) != sorted(records, key=lambda r: r["relation_id"]):
                    raise ValueError("RELATION_ADDRESS_BINDING_CHANGED")
                build = result.get("build")
                if build:
                    target = (self.store.root / build["directory"]).resolve()
                    if not target.is_relative_to(self.home.resolve()):
                        raise ValueError("BUILD_PATH_OUTSIDE_WORKBENCH")
                    for item in build["files"]:
                        file = (target / item["path"]).resolve()
                        if not file.is_relative_to(target):
                            raise ValueError("BUILD_FILE_OUTSIDE_KIT")
                        content = file.read_bytes()
                        if sha256_bytes(content) != item["sha256"] or len(content) != item["bytes"]:
                            raise ValueError("BUILD_ARTIFACT_CHANGED")
                    manifest_ref = build.get("manifest")
                    version = tuple(int(x) for x in result.get("controller_version", "0.0.0").split("."))
                    if manifest_ref is None and version >= (2, 0, 2):
                        raise ValueError("BUILD_MANIFEST_BINDING_MISSING")
                    if manifest_ref is None:
                        # Older finalized kits have no separate manifest descriptor,
                        # but their exact manifest is reconstructible from this bound result.
                        legacy_manifest = {k: v for k, v in build.items()
                                           if k not in {"directory", "viewer", "manifest"}}
                        expected = (canonical_json(legacy_manifest) + "\n").encode("utf-8")
                        if (target / "BUILD_MANIFEST.json").read_bytes() != expected:
                            raise ValueError("BUILD_MANIFEST_CHANGED")
                    if manifest_ref is not None:
                        manifest_file = (target / manifest_ref["path"]).resolve()
                        if not manifest_file.is_relative_to(target) or manifest_file.name != "BUILD_MANIFEST.json":
                            raise ValueError("BUILD_MANIFEST_PATH_INVALID")
                        manifest_bytes = manifest_file.read_bytes()
                        if len(manifest_bytes) != manifest_ref["bytes"] or sha256_bytes(manifest_bytes) != manifest_ref["sha256"]:
                            raise ValueError("BUILD_MANIFEST_CHANGED")
                for ref in result.get("generated_sources", []):
                    if self.store.source_by_id(ref["source_id"])["digest"] != ref["digest"]:
                        raise ValueError("GENERATED_SOURCE_BINDING_CHANGED")
            base["workbench"] = {"analyses": len(rows), "committed_results": len(results)}
        except (ValueError, KeyError, OSError) as error:
            base["errors"].append(str(error)); base["ok"] = False
        return base
