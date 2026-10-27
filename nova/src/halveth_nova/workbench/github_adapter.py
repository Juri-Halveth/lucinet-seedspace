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
    commit = api(root + "/commits/" + quote(ref or "HEAD", safe=""))
    sha = commit["sha"]
    tree = api(root + "/git/trees/" + sha + "?recursive=1")
    save(f"github/{owner}/{repo}/{sha}/commit.json", {"sha": sha, "parents": commit["parents"], "commit": commit["commit"]}, commit=sha)
    save(f"github/{owner}/{repo}/{sha}/tree.json", tree, commit=sha)
    for name, endpoint in (("branches", "/branches?per_page=100"), ("pulls", "/pulls?state=all&per_page=30"),
                           ("issues", "/issues?state=all&per_page=30"), ("history", "/commits?per_page=30&sha=" + sha)):
        rows = api(root + endpoint)
        save(f"github/{owner}/{repo}/{sha}/{name}.json", rows, commit=sha, coverage="FIRST_PAGE_ONLY")
    eligible = [r for r in tree.get("tree", []) if r.get("type") == "blob" and r.get("size", 0) <= 100000
                and re.search(r"\.(md|py|mjs|js|ts|json|toml)$", r["path"], re.I)
                and not any(x in r["path"].lower() for x in (".env", "secret", "credential", "token", "package-lock"))]
    eligible.sort(key=lambda r: (0 if r["path"].lower().endswith("readme.md") else 1, r["path"]))
    for row in eligible[:max_files]:
        blob = api(root + "/git/blobs/" + row["sha"])
        data = base64.b64decode(blob["content"], validate=False)
        if len(data) > 100000:
            raise ValueError("GITHUB_BLOB_SIZE_CHANGED")
        rec = store.ingest_bytes(f"github/{owner}/{repo}/{sha}/{row['path']}", data,
                                 tags=["github", "source"], metadata={"commit": sha, "git_blob": row["sha"],
                                 "retrieved_at": utc_now(), "data_class": "INTERNAL_PSEUDONYMIZED"})
        captured.append(rec["source_id"])
    return {"captured": captured, "commit": sha, "eligible_files": len(eligible), "files_read": min(len(eligible), max_files),
            "coverage": "BOUNDED_TREE_AND_FIRST_PAGE_HISTORY", "tree_truncated": tree.get("truncated", False),
            "omitted_file_count": max(0, len(eligible) - max_files), "network_action": "GITHUB_GET_ONLY"}
