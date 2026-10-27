"""Finite, injective structural retrieval; labels do not establish identity."""
from __future__ import annotations

import re
from typing import Any

from ..jsonutil import sha256_json

CONTRACT = "nova.concept-graph.v1"
ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,119}\Z")
SEMANTICS = {
    "OBSERVES": "declared observation of the target; no truth or independence implied",
    "RELAYS": "declared forwarding dependency on the target; no new observation implied",
    "REACTS_TO": "declared reaction to the target; no observation of its underlying referent implied",
    "CALLS": "syntactic call-site dependency; no runtime execution implied",
    "IMPORTS": "syntactic import dependency; no successful loading implied",
    "DERIVED_FROM": "a representation derived from the target; source authority is not inherited",
}
DEFINITIONS = {k: {"id": "nova.relation." + k.lower(), "version": "1.0.0", "semantics": v}
               for k, v in SEMANTICS.items()}


def closed(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - optional:
        raise ValueError("INVALID_CLOSED_RECORD")


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("INVALID_ASCII_ID")
    return value


def validate_graph(graph: Any) -> dict[str, Any]:
    closed(graph, {"contract", "id", "domain", "nodes", "edges"},
           {"description", "coverage", "unknowns", "observations"})
    if graph["contract"] != CONTRACT:
        raise ValueError("UNSUPPORTED_GRAPH_CONTRACT")
    identifier(graph["id"])
    if not isinstance(graph["domain"], str) or not graph["domain"]:
        raise ValueError("GRAPH_DOMAIN_REQUIRED")
    if not isinstance(graph["nodes"], list) or not 1 <= len(graph["nodes"]) <= 256:
        raise ValueError("GRAPH_NODE_LIMIT")
    if not isinstance(graph["edges"], list) or len(graph["edges"]) > 1024:
        raise ValueError("GRAPH_EDGE_LIMIT")
    nodes = {}
    for node in graph["nodes"]:
        closed(node, {"id", "kind", "label"}, {"aliases", "scope", "definition", "attributes"})
        key = identifier(node["id"])
        identifier(node["kind"])
        if key in nodes or not isinstance(node["label"], str):
            raise ValueError("INVALID_OR_DUPLICATE_NODE")
        aliases = node.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            raise ValueError("INVALID_ALIASES")
        nodes[key] = node
    edges = set()
    for edge in graph["edges"]:
        closed(edge, {"id", "from", "to", "predicate"}, {"state", "definition", "evidence"})
        key = identifier(edge["id"])
        if key in edges or edge["from"] not in nodes or edge["to"] not in nodes:
            raise ValueError("UNBOUND_OR_DUPLICATE_EDGE")
        if edge["predicate"] not in DEFINITIONS:
            raise ValueError("UNREGISTERED_RELATION_DEFINITION")
        if "definition" in edge and edge["definition"] != DEFINITIONS[edge["predicate"]]:
            raise ValueError("RELATION_DEFINITION_MISMATCH")
        edges.add(key)
    for row in graph.get("unknowns", []):
        closed(row, {"field", "referent", "scope", "question"}, {"resolver", "definition"})
        if not all(isinstance(row[k], str) and row[k] for k in ("field", "referent", "scope", "question")):
            raise ValueError("UNBOUND_UNKNOWN")
    sha256_json(graph)  # Reject non-JSON/nonfinite values before any materialization.
    return graph


def structural_match(pattern: dict, graph: dict, *, budget: int = 50000, limit: int = 20) -> dict:
    validate_graph(pattern); validate_graph(graph)
    if type(budget) is not int or not 1 <= budget <= 1000000 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("INVALID_MATCH_BUDGET")
    if len(pattern["nodes"]) > 8:
        raise ValueError("PATTERN_NODE_LIMIT_8")
    pn = {n["id"]: n for n in pattern["nodes"]}
    gn = {n["id"]: n for n in graph["nodes"]}
    ge = {(e["from"], e["predicate"], e["to"]) for e in graph["edges"]}
    degree = {n: sum(e["from"] == n or e["to"] == n for e in pattern["edges"]) for n in pn}
    order = sorted(pn, key=lambda n: (-degree[n], n))
    candidates = {n: sorted(k for k in gn if gn[k]["kind"] == pn[n]["kind"] and
                          gn[k].get("definition") == pn[n].get("definition")) for n in pn}
    found, visits, stopped = [], 0, False

    def descend(mapping: dict[str, str]) -> None:
        nonlocal visits, stopped
        if stopped:
            return
        if len(mapping) == len(order):
            found.append(dict(mapping))
            if len(found) >= limit:
                stopped = True
            return
        node = order[len(mapping)]
        for target in candidates[node]:
            visits += 1
            if visits > budget:
                stopped = True
                return
            if target in mapping.values():
                continue
            trial = {**mapping, node: target}
            if all((trial[e["from"]], e["predicate"], trial[e["to"]]) in ge
                   for e in pattern["edges"] if e["from"] in trial and e["to"] in trial):
                descend(trial)

    descend({})
    return {"contract": "nova.structural-match.v1", "pattern_digest": sha256_json(pattern),
            "graph_digest": sha256_json(graph), "mappings": found, "visited": min(visits, budget),
            "coverage": "FINITE_LIMIT_REACHED" if stopped else "EXHAUSTED_DECLARED_SEARCH_SPACE",
            "equality": "injective kind/definition/labelled-edge subgraph; names ignored",
            "meaning": "STRUCTURE_MATCH_ONLY", "cross_domain": graph["domain"] != pattern["domain"]}


def unknown_key(row: dict) -> str:
    # Same wording alone does not merge referents, domains or definitions.
    return "unknown_" + sha256_json({k: row.get(k) for k in ("field", "referent", "scope", "definition")})[:24]


def addressed_relations(graph: dict, *, source_id: str, source_digest: str, run_id: str,
                        recorded_at: str, evidence_state: str) -> list[dict]:
    """Materialize new relation assertions; never change the bound source graph."""
    graph_digest = sha256_json(graph)
    nodes = {n["id"]: (i, n) for i, n in enumerate(graph["nodes"])}
    records = []
    for edge in graph["edges"]:
        def endpoint(key: str, role: str) -> dict:
            index, node = nodes[key]
            return {"role": role, "kind": node["kind"], "id": graph["id"] + ":" + key,
                    "digest": sha256_json(node), "semantic_address": {"graph_digest": graph_digest,
                        "field_locator": "/nodes/" + str(index), "referent": node["label"],
                        "scope": graph["domain"], "representation": "PARSED_CANONICAL_GRAPH_VALUE"}}
        definition = {**DEFINITIONS[edge["predicate"]], "arity": 2, "direction": "DIRECTED_DECLARED",
                      "endpoint_kinds": "EXPLICIT_NODE_KINDS", "transitive": False,
                      "authority_effect": "NONE", "time_rule": "SOURCE_EVENT_TIME_UNKNOWN_UNLESS_SEPARATELY_BOUND"}
        rid = run_id + ":" + source_id + ":" + graph["id"] + ":" + edge["id"]
        records.append({"contract": "nova.addressed-relation.v1", "relation_id": rid,
                        "relation_type": edge["predicate"], "definition": definition,
                        "definition_digest": sha256_json(definition), "left": endpoint(edge["from"], "SUBJECT"),
                        "right": endpoint(edge["to"], "OBJECT"), "direction": "DIRECTED_DECLARED",
                        "scope": graph["domain"], "event_time": "UNKNOWN", "recorded_at": recorded_at,
                        "time_basis": "producer UTC wall clock; source event time not inferred",
                        "evidence_state": evidence_state, "source_refs": [{"source_id": source_id, "digest": source_digest}],
                        "authority_effect": "NONE", "write_domain_id": rid})
    return records
