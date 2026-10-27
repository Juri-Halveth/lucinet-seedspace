from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATUS_WEIGHT = {
    "active": 1.0,
    "historical": 0.82,
    "superseded": 0.60,
    "retracted": 0.22,
}


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", normalize(text), flags=re.UNICODE)


def _line_hit(text: str, query: str) -> tuple[int, int, str]:
    q = normalize(query)
    qtokens = tokens(query)
    lines = text.splitlines() or [""]
    hit_index = 0
    for i, line in enumerate(lines):
        nline = normalize(line)
        if (q and q in nline) or (qtokens and any(t in nline for t in qtokens)):
            hit_index = i
            break
    start = max(0, hit_index - 1)
    end = min(len(lines), hit_index + 2)
    excerpt = "\n".join(lines[start:end])[:800]
    return start + 1, end, excerpt


@dataclass(frozen=True)
class SearchHit:
    source_id: str
    locator: str
    digest: str
    status: str
    score: float
    line_start: int | None
    line_end: int | None
    excerpt: str
    usable_as_current: bool
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "digest": self.digest,
            "status": self.status,
            "score": round(self.score, 6),
            "line_start": self.line_start,
            "line_end": self.line_end,
            "excerpt": self.excerpt,
            "usable_as_current": self.usable_as_current,
            "tags": self.tags,
        }


def score_candidate(query: str, haystack: str, status: str) -> float:
    nq = normalize(query)
    nh = normalize(haystack)
    if not nq or not nh:
        return 0.0
    qtokens = tokens(query)
    htokens = set(tokens(haystack))
    exact = 1.0 if nq in nh else 0.0
    token_hits = sum(1 for t in qtokens if t in htokens)
    coverage = token_hits / max(1, len(set(qtokens)))
    freq = min(12, sum(nh.count(t) for t in set(qtokens)))
    raw = exact * 8.0 + coverage * 6.0 + math.log1p(freq) * 1.4
    return raw * STATUS_WEIGHT.get(status, 0.5)


def searchable_text(locator: str, tags: list[str], metadata: dict[str, Any], content: bytes) -> tuple[str, bool]:
    try:
        body = content.decode("utf-8", errors="strict")
        is_text = True
    except UnicodeDecodeError:
        body = ""
        is_text = False
    meta = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    combined = "\n".join([locator, " ".join(tags), meta, body])
    return combined, is_text


def search_sources(
    query: str,
    records: Iterable[dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
    object_dir: Path,
    limit: int = 20,
    include_retracted: bool = True,
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for record in records:
        sid = record["source_id"]
        status = statuses.get(sid, {"status": "active"})["status"]
        if status == "retracted" and not include_retracted:
            continue
        obj = object_dir / record["digest"]
        if not obj.is_file():
            continue
        content = obj.read_bytes()
        haystack, is_text = searchable_text(record["locator"], record.get("tags", []), record.get("metadata", {}), content)
        score = score_candidate(query, haystack, status)
        if score <= 0:
            continue
        if is_text:
            text = content.decode("utf-8")
            ls, le, excerpt = _line_hit(text, query)
        else:
            ls = le = None
            excerpt = "[binary source] " + record["locator"]
        hits.append(SearchHit(
            source_id=sid,
            locator=record["locator"],
            digest=record["digest"],
            status=status,
            score=score,
            line_start=ls,
            line_end=le,
            excerpt=excerpt,
            usable_as_current=status in {"active", "historical"},
            tags=list(record.get("tags", [])),
        ))
    hits.sort(key=lambda h: (-h.score, h.locator, h.source_id))
    return hits[:max(1, limit)]
