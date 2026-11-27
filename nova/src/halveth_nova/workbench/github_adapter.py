"""Explicit, bounded read-only GitHub input. gh owns authentication; no token handling."""
from __future__ import annotations

import base64
import json
import re
import subprocess
from typing import Any

from ..jsonutil import canonical_json, strict_loads
from ..store import NovaStore, utc_now

NAME = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
SNAPSHOT_KIND = "NOVA_GITHUB_REFERENCE_SNAPSHOT_V1"


def _selection_state(store: NovaStore, scope: str) -> list[tuple[str, str]]:
    statuses = store.status_map()
    return sorted((row["source_id"], statuses[row["source_id"]]["status"])
                  for row in store.sources()
                  if row.get("metadata", {}).get("github_ref_scope") == scope)


def api(path: str, *, limit: int = 4_000_000) -> Any:
    # No arbitrary endpoint/hostname, shell, writes, pagination or workflow invocation.
    result = subprocess.run(["gh", "api", "--hostname", "github.com", "--method", "GET", path], capture_output=True, timeout=35, shell=False)
    if result.returncode:
        raise RuntimeError("GITHUB_READ_UNAVAILABLE")
    if len(result.stdout) > limit:
        raise ValueError("GITHUB_RESPONSE_LIMIT")
    return strict_loads(result.stdout.decode("utf-8"))


def inventory(store: NovaStore, owner: str, *, repo: str | None = None, ref: str | None = None,
              max_files: int = 24, max_repos: int = 100) -> dict:
    if not NAME.fullmatch(owner) or (repo is not None and not NAME.fullmatch(repo)):
        raise ValueError("INVALID_GITHUB_SCOPE")
    if not 1 <= max_files <= 100 or not 1 <= max_repos <= 100:
        raise ValueError("GITHUB_BUDGET_LIMIT")
    if ref is not None and not re.fullmatch(r"[A-Za-z0-9_./-]{1,160}", ref):
        raise ValueError("INVALID_GITHUB_REF")
    captured = []

    def save(locator: str, value: Any, **metadata: Any) -> None:
        rec = store.ingest_bytes(locator, (canonical_json(value) + "\n").encode("utf-8"),
                                 tags=["github", "metadata"], metadata={"retrieved_at": utc_now(), **metadata})
        captured.append(rec["source_id"])

    if repo is None:
        rows = api(f"users/{owner}/repos?per_page={max_repos}&sort=updated")
        selected = [{k: row.get(k) for k in ("full_name", "description", "default_branch", "html_url", "pushed_at", "archived")} for row in rows]
        save(f"github/{owner}/repository-inventory.json", selected)
        return {"captured": captured, "repos": len(selected), "coverage": "FIRST_PAGE_ONLY",
                "page_limit": max_repos, "action": "READ_ONLY_METADATA"}
    root = f"repos/{owner}/{repo}"
    from urllib.parse import quote
    requested_ref = ref or "HEAD"
    pinned = bool(re.fullmatch(r"[0-9a-fA-F]{40}", requested_ref))
    # HEAD and the explicit default branch share one currentness scope.
    resolved_ref = requested_ref
    if requested_ref == "HEAD":
        resolved_ref = api(root)["default_branch"]
        if not isinstance(resolved_ref, str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,160}", resolved_ref):
            raise ValueError("INVALID_GITHUB_DEFAULT_BRANCH")
    if resolved_ref.startswith("refs/heads/"):
        resolved_ref = resolved_ref[len("refs/heads/"):]
    scope = f"github/{owner.casefold()}/{repo.casefold()}/ref/{quote(resolved_ref, safe='')}"
    with store.write_lock():
        expected_selection = _selection_state(store, scope)
    # Resolve the exact selected branch, even if the repository changes its
    # default branch between the metadata request and this commit request.
    commit = api(root + "/commits/" + quote(resolved_ref, safe=""))
    sha = commit["sha"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("INVALID_GITHUB_COMMIT")
    if pinned and sha != requested_ref.lower():
        raise ValueError("GITHUB_PINNED_COMMIT_MISMATCH")
    tree = api(root + "/git/trees/" + sha + "?recursive=1")
    prefix = f"{scope}/{sha}"
    staged = []

    def stage(path: str, value: Any, **metadata: Any) -> None:
        staged.append((path, (canonical_json(value) + "\n").encode("utf-8"), ["github", "metadata"], metadata))

    stage("commit.json", {"sha": sha, "parents": commit["parents"], "commit": commit["commit"]})
    stage("tree.json", tree)
    for name, endpoint in (("branches", "/branches?per_page=100"), ("pulls", "/pulls?state=all&per_page=30"),
                           ("issues", "/issues?state=all&per_page=30"), ("history", "/commits?per_page=30&sha=" + sha)):
        rows = api(root + endpoint)
        stage(name + ".json", rows, coverage="FIRST_PAGE_ONLY")
    eligible = [r for r in tree.get("tree", []) if r.get("type") == "blob" and r.get("size", 0) <= 100000
                and re.search(r"\.(md|py|mjs|js|ts|json|toml)$", r["path"], re.I)
                and not any(x in r["path"].lower() for x in (".env", "secret", "credential", "token", "package-lock"))]
    eligible.sort(key=lambda r: (0 if r["path"].lower().endswith("readme.md") else 1, r["path"]))
    for row in eligible[:max_files]:
        blob = api(root + "/git/blobs/" + row["sha"])
        data = base64.b64decode(blob["content"], validate=False)
        if len(data) > 100000:
            raise ValueError("GITHUB_BLOB_SIZE_CHANGED")
        staged.append(("files/" + row["path"], data, ["github", "source"],
                       {"git_blob": row["sha"], "source_path": row["path"], "data_class": "INTERNAL_PSEUDONYMIZED"}))
    # All bounded GETs must complete before the prior reference selection changes.
    # The lock excludes another successful capture of this reference while committing.
    with store.write_lock():
        if _selection_state(store, scope) != expected_selection:
            raise RuntimeError("GITHUB_REFERENCE_CHANGED_RETRY")
        observed = utc_now()
        for path, data, tags, metadata in staged:
            rec, _ = store._record_source(f"{prefix}/{path}", data, tags, {
                "commit": sha, "retrieved_at": observed, "github_ref_scope": scope,
                "github_requested_ref": requested_ref, "github_resolved_ref": resolved_ref,
                "github_snapshot_kind": SNAPSHOT_KIND, **metadata})
            captured.append(rec["source_id"])
        statuses = store.status_map()
        for row in store.sources():
            sid = row["source_id"]
            state = statuses[sid]["status"]
            if state == "retracted":
                continue
            metadata = row.get("metadata", {})
            if metadata.get("github_ref_scope") == scope:
                if pinned:
                    if sid in captured and state != "historical":
                        store._set_status_unlocked(sid, "historical", note="Explicit immutable GitHub commit snapshot; no current branch selection")
                elif sid not in captured and state in {"active", "historical"}:
                    store._set_status_unlocked(sid, "superseded", note=f"GitHub reference capture replaced by {sha}")
            elif (metadata.get("github_snapshot_kind") is None
                  and "github" in row.get("tags", [])
                  and re.fullmatch(rf"github/{re.escape(owner)}/{re.escape(repo)}/[0-9a-f]{{40}}/.+", row["locator"], re.I)
                  and state == "active" and not pinned):
                # Old captures did not record a requested ref. Preserve them without
                # guessing which branch they described or labeling them current.
                store._set_status_unlocked(sid, "historical", note="Legacy GitHub capture: reference unknown; exact bytes retained")
    return {"captured": captured, "commit": sha, "eligible_files": len(eligible), "files_read": min(len(eligible), max_files),
            "coverage": "BOUNDED_TREE_AND_FIRST_PAGE_HISTORY", "tree_truncated": tree.get("truncated", False),
            "omitted_file_count": max(0, len(eligible) - max_files), "network_action": "GITHUB_GET_ONLY",
            "reference": resolved_ref, "currentness_scope": scope,
            "selection": "HISTORICAL_PINNED_COMMIT" if pinned else "LATEST_SUCCESSFUL_BOUNDED_CAPTURE"}
