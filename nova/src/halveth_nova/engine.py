from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .model import CLAIM_STATES, RUN_MODES, Claim
from .search import search_sources
from .store import NovaStore, utc_now

RECEIPT_CONTRACT = "halveth.nova.research-receipt.v1"


class NovaEngine:
    def __init__(self, workspace: Path | str):
        self.store = NovaStore(workspace)

    def init(self, name: str | None = None) -> dict[str, Any]:
        return self.store.init(name)

    def ingest(self, path: Path | str, **kwargs: Any) -> list[dict[str, Any]]:
        return self.store.ingest_path(path, **kwargs)

    def search(self, query: str, *, limit: int = 20, include_retracted: bool = True) -> list[dict[str, Any]]:
        self.store.require()
        hits = search_sources(query, self.store.sources(), self.store.status_map(), self.store.objects, limit, include_retracted)
        return [h.to_dict() for h in hits]

    def run(
        self,
        query: str,
        *,
        mode: str = "FLOW",
        limit: int = 10,
        claims: list[Claim] | None = None,
        open_questions: list[str] | None = None,
        artifacts: list[str] | None = None,
        next_seed: str = "",
        note: str = "",
        expected_previous_hash: str | None = None,
    ) -> dict[str, Any]:
        self.store.require()
        if mode not in RUN_MODES:
            raise ValueError(f"invalid mode: {mode}")
        hits = self.search(query, limit=limit, include_retracted=True)
        source_map = {s["source_id"]: s for s in self.store.sources()}
        status_map = self.store.status_map()
        bindings = []
        for hit in hits:
            src = source_map[hit["source_id"]]
            bindings.append({
                "source_id": src["source_id"],
                "locator": src["locator"],
                "digest": src["digest"],
                "status": status_map[src["source_id"]]["status"],
                "score": hit["score"],
                "line_start": hit["line_start"],
                "line_end": hit["line_end"],
            })
        claim_rows = []
        for claim in claims or []:
            if claim.state not in CLAIM_STATES:
                raise ValueError(f"invalid claim state: {claim.state}")
            for sid in claim.evidence:
                self.store.source_by_id(sid)
            claim_rows.append(claim.to_dict())
        latest = self.store.latest_ledger()
        receipt = {
            "contract": RECEIPT_CONTRACT,
            "run_id": "run_" + uuid.uuid4().hex,
            "created_at": utc_now(),
            "mode": mode,
            "query": query,
            "input_sources": bindings,
            "claims": claim_rows,
            "open_questions": list(open_questions or []),
            "artifacts": list(artifacts or []),
            "relations_visible": [r["relation_id"] for r in self.store.relations()],
            "predecessor_run_id": latest["receipt"]["run_id"] if latest else None,
            "predecessor_entry_hash": latest["entry_hash"] if latest else None,
            "next_seed": next_seed,
            "note": note,
        }
        return self.store.append_receipt(receipt, expected_previous_hash=expected_previous_hash)

    def resume(self) -> dict[str, Any] | None:
        self.store.require()
        verification = self.store.verify()
        if not verification["ok"]:
            raise RuntimeError("cannot resume invalid workspace: " + "; ".join(verification["errors"]))
        resume = self.store.read_resume()
        if not resume:
            return None
        ledger = self.store.ledger()
        last = ledger[-1]
        return {
            **resume,
            "query": last["receipt"]["query"],
            "mode": last["receipt"]["mode"],
            "open_questions": last["receipt"].get("open_questions", []),
            "artifacts": last["receipt"].get("artifacts", []),
            "predecessor_run_id": last["receipt"].get("predecessor_run_id"),
        }
