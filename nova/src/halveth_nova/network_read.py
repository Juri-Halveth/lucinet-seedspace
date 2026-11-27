"""Read one search result by exact identity and digest without changing a workspace.

Public results resolve only within NOVA's fixed public index. Local results
resolve only within the explicitly selected, already initialized workspace.
Content is data; no discovered command, URL or source is executed.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from http.client import HTTPException
from urllib.error import HTTPError, URLError

from .jsonutil import canonical_json
from .model import SOURCE_STATUSES
from .network_search import (
    MAX_LOCAL_SOURCE_BYTES,
    MAX_LOCAL_SOURCES,
    PUBLIC_INDEX_URL,
    _check_local_path,
    _check_workspace_paths,
    _index,
    _load_public_index,
)
from .store import utc_now

CONTRACT = "nova.network-read.v1"
MAX_CHARS = 32_000
_DIGEST = re.compile(r"[a-f0-9]{64}")
_LOCAL_ID = re.compile(r"src_[a-f0-9]{20}")


def _arguments(identifier, expected_digest, include_historical, offset, max_chars):
    valid_id = isinstance(identifier, str) and (
        identifier.startswith("local:") and _LOCAL_ID.fullmatch(identifier[6:])
        or identifier.startswith("public:") and 1 <= len(identifier[7:]) <= 600
    )
    if (not valid_id or not isinstance(expected_digest, str)
            or not _DIGEST.fullmatch(expected_digest)
            or type(include_historical) is not bool
            or type(offset) is not int or offset < 0
            or type(max_chars) is not int or not 1 <= max_chars <= MAX_CHARS):
        raise ValueError("NETWORK_READ_ARGUMENT_INVALID")


def _finish(result, text, offset, max_chars):
    if offset > len(text):
        return {**result, "state": "ERROR", "error": "OFFSET_OUT_OF_RANGE"}
    page = text[offset:offset + max_chars]
    end = offset + len(page)
    more = end < len(text)
    return {**result, "state": "OK", "content": {
        "text": page, "offset": offset, "returned_chars": len(page),
        "total_chars": len(text), "next_offset": end if more else None,
        "has_more": more, "truncated": offset > 0 or more,
    }}


def _eligibility(result, expected_digest, include_historical):
    if result["digest"] != expected_digest:
        return {**result, "state": "CHANGED", "error": "SOURCE_DIGEST_MISMATCH"}
    if not include_historical and not result["usable_as_current"]:
        return {**result, "state": "NOT_CURRENT", "error": "SOURCE_NOT_CURRENT"}
    return None


def _local_snapshot(store):
    _check_workspace_paths(store)
    rows = store.sources()
    if not isinstance(rows, list) or len(rows) > MAX_LOCAL_SOURCES:
        raise ValueError("LOCAL_SOURCE_COUNT_LIMIT")
    sources = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("source_id"), str)
                or not _LOCAL_ID.fullmatch(row["source_id"])
                or not isinstance(row.get("metadata", {}), dict)):
            raise ValueError("LOCAL_SOURCE_METADATA_INVALID")
        if row["source_id"] in sources:
            raise ValueError("LOCAL_DUPLICATE_SOURCE_ID")
        sources[row["source_id"]] = row
    statuses = store.status_map()
    if not isinstance(statuses, dict) or set(statuses) != set(sources):
        raise ValueError("LOCAL_SOURCE_METADATA_CHANGED")
    for status in statuses.values():
        if (not isinstance(status, dict) or not isinstance(status.get("status"), str)
                or status["status"] not in SOURCE_STATUSES):
            raise ValueError("LOCAL_SOURCE_STATUS_INVALID")
    return sources, statuses


def _local_bytes(store, source):
    digest, size = source.get("digest"), source.get("byte_length")
    if (not isinstance(digest, str) or not _DIGEST.fullmatch(digest)
            or type(size) is not int or not 0 <= size <= MAX_LOCAL_SOURCE_BYTES):
        raise ValueError("LOCAL_SOURCE_METADATA_INVALID")
    path = store.objects / digest
    _check_workspace_paths(store)
    before = _check_local_path(path)
    if before is None:
        raise ValueError("LOCAL_SOURCE_MISSING_OR_TOO_LARGE")
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_LOCAL_SOURCE_BYTES:
        raise ValueError("LOCAL_SOURCE_MISSING_OR_TOO_LARGE")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_LOCAL_SOURCE_BYTES
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError("LOCAL_SOURCE_OBJECT_CHANGED_DURING_READ")
        raw = stream.read(MAX_LOCAL_SOURCE_BYTES + 1)
    after = _check_local_path(path)
    if after is None:
        raise ValueError("LOCAL_SOURCE_OBJECT_CHANGED_DURING_READ")
    if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
        raise ValueError("LOCAL_SOURCE_OBJECT_CHANGED_DURING_READ")
    if len(raw) > MAX_LOCAL_SOURCE_BYTES:
        raise ValueError("LOCAL_SOURCE_MISSING_OR_TOO_LARGE")
    if len(raw) != size:
        raise ValueError("LOCAL_SOURCE_BYTE_LENGTH_CHANGED")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("LOCAL_SOURCE_BYTES_CHANGED")
    return raw


def _local_read(engine, result, expected_digest, include_historical, offset, max_chars):
    from .workbench.controller import Workbench

    store = engine.store
    _check_workspace_paths(store)
    store.require()
    sources, statuses = _local_snapshot(store)
    sid = result["source_id"]
    source = sources.get(sid)
    if source is None:
        return {**result, "state": "NOT_FOUND", "error": "SOURCE_NOT_FOUND"}
    # Construction only binds the same workspace paths; it does not initialize
    # files or run a controller. Pass the already read records explicitly.
    effective = Workbench(store.root).effective_status(sid, statuses, sources)
    observed = source.get("added_at")
    locator = source.get("locator")
    if (not isinstance(observed, str) or not observed or len(observed) > 64
            or not isinstance(locator, str) or not locator or len(locator) > 4096):
        raise ValueError("LOCAL_SOURCE_METADATA_INVALID")
    result.update({
        "digest": source["digest"], "digest_scope": "LOCAL_STORED_SOURCE_BYTES",
        "status": statuses[sid]["status"], "effective_status": effective,
        "usable_as_current": effective == "active", "observedAt": observed,
        "revision": sid,
        "source": {"locator": locator, "revision": sid, "observedAt": observed,
                   "byte_length": source["byte_length"]},
        "consistency": "METADATA_COMPARED_BEFORE_AND_AFTER_READ_NOT_ATOMIC",
    })
    rejected = _eligibility(result, expected_digest, include_historical)
    if rejected is not None:
        return rejected
    raw = _local_bytes(store, source)
    current_sources, current_statuses = _local_snapshot(store)
    if sources != current_sources or statuses != current_statuses:
        raise ValueError("LOCAL_SOURCE_METADATA_CHANGED")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError("SOURCE_NOT_UTF8") from None
    return _finish(result, text, offset, max_chars)


def _public_read(result, expected_digest, include_historical, offset, max_chars, loader):
    raw = (_load_public_index if loader is None else loader)()
    index = _index(raw)
    doc = next((doc for doc in index["documents"] if doc["id"] == result["source_id"]), None)
    if doc is None:
        return {**result, "state": "NOT_FOUND", "error": "SOURCE_NOT_FOUND"}
    current = not doc["historical"] and doc["editorialState"] == "CURRENT"
    status = ("active" if current else "withdrawn"
              if doc["editorialState"] == "WITHDRAWN_FROM_PORTFOLIO" else "historical")
    result.update({
        "digest": hashlib.sha256(canonical_json(doc).encode("utf-8")).hexdigest(),
        "digest_scope": "PUBLIC_INDEX_DOCUMENT_NOT_ORIGINAL_SOURCE_FILE",
        "status": status, "effective_status": status, "usable_as_current": current,
        "observedAt": doc["source"]["observedAt"], "revision": doc["source"].get("revision"),
        "source": {key: doc["source"][key]
                   for key in ("url", "revision", "observedAt", "scope") if key in doc["source"]},
        "index": {"url": PUBLIC_INDEX_URL, "revision": index["revision"],
                  "observedAt": index["observedAt"], "sha256": hashlib.sha256(raw).hexdigest()},
    })
    rejected = _eligibility(result, expected_digest, include_historical)
    if rejected is not None:
        return rejected
    return _finish(result, doc["text"], offset, max_chars)


def _error_code(error, public):
    if isinstance(error, ValueError) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", str(error)):
        return str(error)
    if isinstance(error, HTTPError):
        error.close()
        return "PUBLIC_HTTP_" + str(error.code)
    if isinstance(error, (HTTPException, URLError)):
        return "PUBLIC_TRANSPORT_ERROR" if public else "LOCAL_SOURCE_READ_ERROR"
    if isinstance(error, UnicodeError):
        return "PUBLIC_INDEX_ENCODING_INVALID" if public else "LOCAL_SOURCE_ENCODING_INVALID"
    if isinstance(error, PermissionError):
        return "PUBLIC_TRANSPORT_ERROR" if public else "LOCAL_SOURCE_READ_DENIED"
    if isinstance(error, (KeyError, TypeError, AttributeError, RecursionError)):
        return "PUBLIC_INDEX_SCHEMA_INVALID" if public else "LOCAL_SOURCE_METADATA_INVALID"
    return "PUBLIC_SOURCE_READ_ERROR" if public else "LOCAL_SOURCE_READ_ERROR"


def network_read(engine, identifier, expected_digest, *, include_historical=False,
                 offset=0, max_chars=6000, loader=None):
    """Resolve an exact result and return a bounded Unicode text page.

    ``loader`` is the same offline Python test seam as network_search's loader;
    it does not add a configurable network address. ``engine`` is not accessed
    for public IDs. Invalid input raises before any source or network access.
    All operational failure responses omit ``content``.
    """
    _arguments(identifier, expected_digest, include_historical, offset, max_chars)
    public = identifier.startswith("public:")
    result = {
        "contract": CONTRACT, "id": identifier,
        "source_id": identifier[7:] if public else identifier[6:],
        "source_scope": "public_description" if public else "local_source",
        "expected_digest": expected_digest, "include_historical": include_historical,
        "readAt": utc_now(), "state": "ERROR",
    }
    try:
        if public:
            return _public_read(result, expected_digest, include_historical, offset, max_chars, loader)
        return _local_read(engine, result, expected_digest, include_historical, offset, max_chars)
    except (ValueError, RuntimeError, OSError, HTTPException, UnicodeError,
            KeyError, TypeError, AttributeError, RecursionError) as error:
        return {**result, "state": "ERROR", "error": _error_code(error, public)}
