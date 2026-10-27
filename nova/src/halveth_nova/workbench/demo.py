from __future__ import annotations

from pathlib import Path

from ..jsonutil import canonical_json
from .controller import Workbench
from .graph import CONTRACT


def scene(key: str, domain: str, labels: list[str]) -> dict:
    return {"contract": CONTRACT, "id": key, "domain": domain,
            "description": "Synthetic declared structure; functional roles, not physical equivalence.",
            "nodes": [{"id": "n" + str(i), "kind": "ACTOR" if i < 3 else "EVENT", "label": label}
                      for i, label in enumerate(labels)],
            "edges": [{"id": "e1", "from": "n0", "to": "n3", "predicate": "OBSERVES"},
                      {"id": "e2", "from": "n1", "to": "n0", "predicate": "RELAYS"},
                      {"id": "e3", "from": "n2", "to": "n1", "predicate": "OBSERVES"}],
            "unknowns": [{"field": "independent_observer_identity", "referent": key, "scope": "declared_scene",
                          "definition": "independent physical origin, not distinct labels",
                          "question": "Which independently authenticated observations exist?",
                          "resolver": "bound observation and identity receipts for this scene"}]}


def run(workspace: str | Path, *, model: str | None = None, node: str | None = None,
        generate_function: bool = False) -> dict:
    bench = Workbench(workspace); bench.engine.init("NOVA Demonstrator")
    folder = bench.store.root / "demo-inputs"
    folder.mkdir(exist_ok=False)
    scenes = [scene("route_scene", "synthetic.route", ["Beobachter Alpha", "Weitergabe Bravo", "Kamera Charlie", "Hilfsweg"]),
              scene("message_scene", "synthetic.messages", ["Account 17", "Repost 4", "Archiv 9", "Beitrag"]),
              scene("signal_scene", "synthetic.signals", ["Detektor 28", "Relais 31", "Prüfer 42", "Impuls"])]
    for g in scenes:
        (folder / (g["id"] + ".json")).write_bytes((canonical_json(g) + "\n").encode("utf-8"))
    (folder / "source-note.txt").write_bytes(
        b"Alpha observes a blocked route. Bravo relays the report from Alpha. Charlie observes Bravo reacting to the report.\n")
    indexed = bench.index([folder], model=model)
    flow = bench.run("Beobachtung Hilfsweg", mode="FLOW")
    atlas = bench.run("Beobachtung Weitergabe Herkunft", mode="ATLAS", pattern=scenes[0])
    deep = bench.run("Beobachtung Weitergabe Herkunft", mode="DEEP", pattern=scenes[0],
                     integration="lagefaden" if node else None, node=node or "node")
    spec = None
    if generate_function:
        spec = {"contract": "nova.pure-build-spec.v1", "description":
                "Implement solve(data). Input is a list of JSON reports. Each report has root_id (string or null) and a label. "
                "Return the number of distinct non-null root_id strings. Multiple labels and copies of the same root count once. "
                "Empty input returns 0. Ignore all other fields. Do not infer physical independence.",
                "cases": [{"id": "empty", "input": [], "expected": 0},
                          {"id": "copy", "input": [{"root_id": "R1", "label": "A"}, {"root_id": "R1", "label": "B"}], "expected": 1},
                          {"id": "unknown", "input": [{"root_id": None, "label": "A"}], "expected": 0},
                          {"id": "mixed", "input": [{"root_id": "Q", "label": "B"}, {"root_id": "Z", "label": "A"}, {"root_id": "Q", "label": "C"}], "expected": 2}]}
    built = bench.run("Beobachtung Weitergabe Herkunft", mode="BUILD", pattern=scenes[0], model=model,
                      integration="lagefaden" if node else None, node=node or "node", build_spec=spec)
    passed = not generate_function or built["result"]["function_build"]["state"] == "TESTED_CANDIDATE"
    return {"contract": "nova.demo-receipt.v1", "outcome": "DEMO_PASSED" if passed else "DEMO_FAILED_GENERATION",
            "indexed": indexed, "runs": [r["ledger"] for r in (flow, atlas, deep, built)],
            "structural_matches": sum(bool(m["mappings"]) for m in atlas["result"]["structural_matches"]),
            "viewer": built["result"]["build"]["viewer"], "build": built["result"]["build"],
            "function_build": built["result"].get("function_build"),
            "integration": built["result"].get("integration"), "verification": bench.verify()}
