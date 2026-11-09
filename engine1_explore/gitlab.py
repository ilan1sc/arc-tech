"""Public GitLab API client with disk cache (data/cache/gitlab). Only search terms leave the machine."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "gitlab"
API = os.getenv("GITLAB_API", "https://gitlab.com/api/v4")
TOKEN = os.getenv("GITLAB_TOKEN")  # optional, raises rate limits


class GitLabUnavailable(RuntimeError):
    pass


def _get(path: str, params: dict | None = None, raw: bool = False):
    key = hashlib.sha256(json.dumps([path, params, raw], sort_keys=True).encode()).hexdigest()[:24]
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = CACHE / f"{key}.json"
    if cp.exists():
        return json.loads(cp.read_text())["data"]
    if os.getenv("ARC_OFFLINE", "0") == "1":
        raise GitLabUnavailable(f"offline, no cache for {path}")
    headers = {"PRIVATE-TOKEN": TOKEN} if TOKEN else {}
    for attempt in range(3):
        try:
            r = httpx.get(f"{API}{path}", params=params, headers=headers, timeout=30, follow_redirects=True)
        except httpx.HTTPError as e:
            if attempt == 2:
                raise GitLabUnavailable(str(e)) from e
            time.sleep(2)
            continue
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")))
            continue
        if r.status_code == 404:
            data = None
        elif r.status_code >= 400:
            raise GitLabUnavailable(f"{r.status_code} {path}")
        else:
            data = r.text[:200_000] if raw else r.json()
        cp.write_text(json.dumps({"path": path, "params": params, "data": data}))
        return data
    raise GitLabUnavailable(f"rate limited: {path}")


def search_projects(term: str, per_page: int = 10) -> list[dict]:
    """Merge GitLab's similarity ordering with star ordering (stars alone surfaces weak matches)."""
    seen, out = set(), []
    for order in ("similarity", "star_count"):
        res = _get("/projects", {"search": term, "per_page": per_page, "order_by": order, "sort": "desc",
                                 "simple": "true", "visibility": "public"}) or []
        for p in res:
            if p["id"] not in seen and not p.get("archived"):
                seen.add(p["id"])
                out.append(p)
    return out


def project(pid: int | str) -> dict | None:
    return _get(f"/projects/{quote(str(pid), safe='')}", {"license": "true", "statistics": "false"})


def head_commit(pid: int, ref: str) -> dict | None:
    return _get(f"/projects/{pid}/repository/commits/{quote(ref, safe='')}")


def tree(pid: int, sha: str, max_pages: int = 3) -> list[dict]:
    items: list[dict] = []
    for page in range(1, max_pages + 1):
        res = _get(f"/projects/{pid}/repository/tree", {"ref": sha, "recursive": "true", "per_page": 100, "page": page}) or []
        items += res
        if len(res) < 100:
            break
    return items


def raw_file(pid: int, path: str, sha: str) -> str | None:
    return _get(f"/projects/{pid}/repository/files/{quote(path, safe='')}/raw", {"ref": sha}, raw=True)


def resolve_url(url: str) -> dict | None:
    """https://gitlab.com/group/sub/project -> project json"""
    path = url.split("gitlab.com/", 1)[-1].strip("/").removesuffix(".git").split("/-/")[0]
    return project(path)
