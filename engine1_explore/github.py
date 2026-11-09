"""Public GitHub client via the `gh` CLI (uses the machine's existing gh login; we never read the token).
Falls back to unauthenticated HTTPS if gh is unavailable. Disk-cached in data/cache/github."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "github"
GH = shutil.which("gh")


class GitHubUnavailable(RuntimeError):
    pass


def _get(path: str, raw: bool = False):
    key = hashlib.sha256(json.dumps([path, raw]).encode()).hexdigest()[:24]
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = CACHE / f"{key}.json"
    if cp.exists():
        return json.loads(cp.read_text())["data"]
    if os.getenv("ARC_OFFLINE", "0") == "1":
        raise GitHubUnavailable(f"offline, no cache for {path}")
    accept = "application/vnd.github.raw" if raw else "application/vnd.github+json"
    if GH:
        r = subprocess.run([GH, "api", "-H", f"Accept: {accept}", path], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            if "404" in r.stderr or "Not Found" in r.stdout:
                data = None
            else:
                raise GitHubUnavailable(f"gh api {path}: {r.stderr.strip()[:200]}")
        else:
            data = r.stdout[:200_000] if raw else json.loads(r.stdout)
    else:
        resp = httpx.get(f"https://api.github.com/{path}", headers={"Accept": accept}, timeout=30)
        if resp.status_code == 404:
            data = None
        elif resp.status_code >= 400:
            raise GitHubUnavailable(f"{resp.status_code} {path}")
        else:
            data = resp.text[:200_000] if raw else resp.json()
    cp.write_text(json.dumps({"path": path, "data": data}))
    return data


def _norm(r: dict) -> dict:
    """Normalize a GitHub repo to the same shape Engine 1 uses for GitLab hits."""
    return {"provider": "github", "id": f"gh:{r['full_name']}", "full_name": r["full_name"], "name": r["name"],
            "name_with_namespace": r["full_name"], "description": r.get("description") or "",
            "web_url": r["html_url"], "star_count": r.get("stargazers_count", 0),
            "last_activity_at": r.get("pushed_at"), "default_branch": r.get("default_branch"),
            "topics": r.get("topics") or [], "archived": r.get("archived", False),
            "license_key": ((r.get("license") or {}).get("spdx_id") or "").lower() or None}


def search_repos(term: str, per_page: int = 10) -> list[dict]:
    q = quote(f"{term} in:name,description,topics archived:false")
    res = _get(f"search/repositories?q={q}&sort=stars&order=desc&per_page={per_page}") or {}
    return [_norm(r) for r in res.get("items", [])]


def repo(full_name: str) -> dict | None:
    r = _get(f"repos/{full_name}")
    return _norm(r) if r else None


def head_commit(full_name: str, ref: str) -> dict | None:
    c = _get(f"repos/{full_name}/commits/{quote(ref, safe='')}")
    return {"id": c["sha"]} if c else None


def tree(full_name: str, sha: str) -> list[dict]:
    t = _get(f"repos/{full_name}/git/trees/{sha}?recursive=1") or {}
    return [{"path": i["path"], "type": "blob" if i["type"] == "blob" else "tree"} for i in t.get("tree", [])][:3000]


def raw_file(full_name: str, path: str, sha: str) -> str | None:
    return _get(f"repos/{full_name}/contents/{quote(path)}?ref={sha}", raw=True)
