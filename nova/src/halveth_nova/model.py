from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SOURCE_STATUSES = {"active", "historical", "superseded", "retracted"}
RELATION_STATES = {"supported", "hypothesis", "contradicted", "unknown", "historical"}
RELATION_TYPES = {
    "DERIVED_FROM", "INSPIRED_BY", "CONTRADICTS", "SUPPORTS", "REUSES",
    "TRANSFORMS", "MIRRORS", "SEMIBRIDGES", "FULLBRIDGES", "PRECEDES",
    "REPLACES", "SPLITS_FROM", "MERGES_WITH", "UNKNOWN_RELATION",
    "CORRECTS", "RETRACTS", "REFERENCES",
}
RUN_MODES = {"FLOW", "ATLAS", "DEEP", "BUILD"}
CLAIM_STATES = {
    "OBSERVED", "SUPPORTED", "DERIVED", "DECLARED", "HYPOTHESIS", "MODEL",
    "METAPHOR", "FICTIONAL_ANALOGY", "USER_REPORTED", "CONTRADICTION",
    "COUNTEREXAMPLE", "UNKNOWN",
}


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    locator: str
    digest: str
    byte_length: int
    media_type: str
    added_at: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceEvent:
    event_id: str
    source_id: str
    status: str
    at: str
    note: str = ""
    superseded_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelationRecord:
    relation_id: str
    subject: str
    predicate: str
    object: str
    state: str
    created_at: str
    evidence: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Claim:
    text: str
    state: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
