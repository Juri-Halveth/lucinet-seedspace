"""Eine lokale Anfrage an eingelesene NOVA-Quellen und öffentliche Beschreibungen."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .jsonutil import canonical_json, strict_loads
from .search import score_candidate
from .store import utc_now

PUBLIC_INDEX_URL = "https://juri-halveth.github.io/universum/api/search.json"
MAX_INDEX_BYTES = 1_000_000
MAX_DOCUMENTS = 2000
MAX_LOCAL_SOURCES = 2000
MAX_LOCAL_SOURCE_BYTES = 8_000_000
TIMEOUT_SECONDS = 8


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        raise ValueError("PUBLIC_REDIRECT_REJECTED")


def _load_public_index() -> bytes:
    # Weder Suchtext noch lokale Daten, Zugangsdaten oder Cookies werden gesendet.
    request = Request(PUBLIC_INDEX_URL, method="GET", headers={
        "Accept": "application/json", "User-Agent": "HALVETH-NOVA-network-search/1"})
    with build_opener(_NoRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
        if response.geturl() != PUBLIC_INDEX_URL or response.status != 200:
            raise ValueError("PUBLIC_ENDPOINT_CHANGED")
        if response.headers.get_content_type() != "application/json":
            raise ValueError("PUBLIC_CONTENT_TYPE_INVALID")
        return response.read(MAX_INDEX_BYTES + 1)


def _text(value, maximum=2048):
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError("PUBLIC_INDEX_SCHEMA_INVALID")
    return value


def _date(value):
    try:
        datetime.fromisoformat(_text(value, 64).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("PUBLIC_INDEX_DATE_INVALID") from None


def _url(value):
    parsed = urlsplit(_text(value))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("PUBLIC_INDEX_URL_INVALID")


def _index(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_INDEX_BYTES:
        raise ValueError("PUBLIC_INDEX_SIZE_LIMIT")
    index = strict_loads(raw.decode("utf-8"))
    if not isinstance(index, dict) or index.get("schema") != "halveth.network-search.v1":
        raise ValueError("PUBLIC_INDEX_SCHEMA_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", _text(index.get("revision"), 64)):
        raise ValueError("PUBLIC_INDEX_REVISION_INVALID")
    _date(index.get("observedAt"))
    documents = index.get("documents")
    if not isinstance(documents, list) or len(documents) > MAX_DOCUMENTS:
        raise ValueError("PUBLIC_DOCUMENT_LIMIT")
    ids = set()
    for doc in documents:
        if not isinstance(doc, dict):
            raise ValueError("PUBLIC_INDEX_SCHEMA_INVALID")
        identifier = _text(doc.get("id"), 600)
        if identifier in ids:
            raise ValueError("PUBLIC_DUPLICATE_ID")
        ids.add(identifier)
        if type(doc.get("historical")) is not bool or doc.get("editorialState") not in {
                "CURRENT", "ARCHIVE", "WITHDRAWN_FROM_PORTFOLIO"}:
            raise ValueError("PUBLIC_INDEX_STATUS_INVALID")
        if doc.get("visibility", "public") not in {"public", "PUBLIC"}:
            raise ValueError("PUBLIC_VISIBILITY_INVALID")
        _url(doc.get("url"))
        for field in ("title", "summary"):
            value = doc.get(field)
            if not isinstance(value, dict) or not value or len(value) > 10:
                raise ValueError("PUBLIC_INDEX_SCHEMA_INVALID")
            for text in value.values():
                _text(text, 6000)
        _text(doc.get("text"), 30000)
        aliases = doc.get("aliases", [])
        if not isinstance(aliases, list) or len(aliases) > 100:
            raise ValueError("PUBLIC_INDEX_SCHEMA_INVALID")
        for alias in aliases:
            _text(alias, 600)
        source = doc.get("source")
        if not isinstance(source, dict):
            raise ValueError("PUBLIC_INDEX_SCHEMA_INVALID")
        _url(source.get("url"))
        _date(source.get("observedAt"))
        _text(source.get("scope"), 300)
        if source.get("revision") is not None:
            _text(source["revision"], 128)
    return index


def _local(engine, query, include_historical, limit):
    engine.store.require()
    sources = engine.store.sources()
    if len(sources) > MAX_LOCAL_SOURCES:
        raise ValueError("LOCAL_SOURCE_COUNT_LIMIT")
    by_id = {source["source_id"]: source for source in sources}
    for source in sources:
        if not re.fullmatch(r"[0-9a-f]{64}", source["digest"]):
            raise ValueError("LOCAL_SOURCE_DIGEST_INVALID")
        path = engine.store.objects / source["digest"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOCAL_SOURCE_BYTES:
            raise ValueError("LOCAL_SOURCE_MISSING_OR_TOO_LARGE")
    hits = engine.search(query, limit=max(1, len(sources)), include_retracted=include_historical)
    hits = [hit for hit in hits if include_historical or hit["status"] == "active"]
    selected = []
    for hit in hits[:limit]:
        source = by_id[hit["source_id"]]
        with (engine.store.objects / hit["digest"]).open("rb") as stream:
            raw = stream.read(MAX_LOCAL_SOURCE_BYTES + 1)
        if len(raw) > MAX_LOCAL_SOURCE_BYTES or hashlib.sha256(raw).hexdigest() != hit["digest"]:
            raise ValueError("LOCAL_SOURCE_BYTES_CHANGED")
        selected.append({**hit, "id": "local:" + hit["source_id"], "source_scope": "local_source",
                         "revision": hit["source_id"], "observedAt": source["added_at"],
                         "digest_scope": "LOCAL_STORED_SOURCE_BYTES"})
    return selected, {"state": "OK", "source_records": len(sources), "matched": len(hits),
                      "returned": len(selected), "truncated": len(hits) > limit,
                      "coverage": "EXPLICITLY_INGESTED_WORKSPACE_SOURCES_ONLY"}


def _public(raw, query, include_historical, limit):
    index = _index(raw)
    hits = []
    eligible = 0
    for doc in index["documents"]:
        current = not doc["historical"] and doc["editorialState"] == "CURRENT"
        if not current and not include_historical:
            continue
        eligible += 1
        text = " ".join([*doc["title"].values(), *doc["summary"].values(), doc["text"], *doc.get("aliases", [])])
        score = score_candidate(query, text, "active" if current else "historical")
        if score <= 0:
            continue
        hits.append({"id": "public:" + doc["id"], "source_id": doc["id"],
                     "source_scope": "public_description", "title": doc["title"], "url": doc["url"],
                     "revision": doc["source"].get("revision"), "observedAt": doc["source"]["observedAt"],
                     "source": doc["source"], "digest": hashlib.sha256(canonical_json(doc).encode()).hexdigest(),
                     "digest_scope": "PUBLIC_INDEX_DOCUMENT_NOT_ORIGINAL_SOURCE_FILE",
                     "status": "active" if current else "withdrawn" if doc["editorialState"] == "WITHDRAWN_FROM_PORTFOLIO" else "historical",
                     "usable_as_current": current, "score": round(score, 6),
                     "excerpt": doc["summary"].get("de", next(iter(doc["summary"].values())))})
    hits.sort(key=lambda hit: (-hit["score"], hit["id"]))
    return hits[:limit], {"state": "OK", "documents": len(index["documents"]), "eligible": eligible,
                          "matched": len(hits), "returned": min(limit, len(hits)), "truncated": len(hits) > limit,
                          "observedAt": index["observedAt"], "revision": index["revision"],
                          "index_sha256": hashlib.sha256(raw).hexdigest(),
                          "coverage": "PUBLIC_INDEX_DESCRIPTIONS_ONLY_NOT_REPOSITORY_FULL_TEXT"}


def network_search(engine, query, *, include_historical=False, limit=20, loader=None):
    """Der injizierbare Loader ist nur eine Python-Testnaht, kein frei wählbarer URL-Parameter."""
    if not isinstance(query, str) or not query.strip() or len(query) > 512 or type(include_historical) is not bool or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("NETWORK_SEARCH_QUERY_OR_LIMIT_INVALID")
    result = {"contract": "nova.network-search.v1", "query": query, "searchedAt": utc_now(),
              "include_historical": include_historical, "limit_per_scope": limit,
              "endpoint": PUBLIC_INDEX_URL, "state": "OK", "scopes": {}, "hits": [],
              "coverage": "DECLARED_WORKSPACE_AND_PUBLIC_INDEX_ONLY; UNINDEXED_FILES_UNKNOWN"}
    for scope in ("local_source", "public_description"):
        try:
            hits, coverage = (_local(engine, query, include_historical, limit) if scope == "local_source"
                              else _public((loader or _load_public_index)(), query, include_historical, limit))
            result["hits"].extend(hits)
            result["scopes"][scope] = coverage
        except (ValueError, RuntimeError, OSError, URLError, UnicodeError, RecursionError, KeyError, TypeError) as error:
            code = "PUBLIC_HTTP_" + str(error.code) if isinstance(error, HTTPError) else type(error).__name__
            if isinstance(error, ValueError) and re.fullmatch(r"[A-Z_]+", str(error)):
                code = str(error)
            result["scopes"][scope] = {"state": "ERROR", "error": code, "coverage": "NOT_SEARCHED_SUCCESSFULLY"}
            result["state"] = "PARTIAL"
    return result
