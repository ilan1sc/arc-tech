"""Bounded repository inspection at a pinned commit. We never claim complete code comprehension."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import github, gitlab

MANIFESTS = ["package.json", "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "go.mod", "pom.xml",
             "build.gradle", "Cargo.toml", "CMakeLists.txt", "composer.json", "Gemfile", "Dockerfile",
             "docker-compose.yml", "docker-compose.yaml", "environment.yml"]
SRC_EXT = (".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".h", ".kt", ".cs", ".php", ".rb", ".dart", ".swift")
LICENSE_PATTERNS = [
    ("AGPL-3.0", r"GNU AFFERO GENERAL PUBLIC LICENSE"),
    ("LGPL", r"GNU LESSER GENERAL PUBLIC LICENSE"),
    ("GPL", r"GNU GENERAL PUBLIC LICENSE"),
    ("Apache-2.0", r"Apache License,?\s+Version 2\.0"),
    ("MPL-2.0", r"Mozilla Public License,?\s+(v\. |Version )?2\.0"),
    ("MIT", r"Permission is hereby granted, free of charge"),
    ("BSD", r"Redistribution and use in source and binary forms"),
    ("EUPL", r"European Union Public Licen[cs]e"),
]


@dataclass
class Excerpt:
    ref: str           # path@sha8  (or api:<field>)
    kind: str          # readme | manifest | license | source | test | tree | metadata
    text: str


@dataclass
class RepoBundle:
    project_id: int | str
    name: str
    web_url: str
    description: str
    sha: str
    default_branch: str
    license_api: str | None
    license_detected: str | None
    stars: int
    last_activity: str | None
    file_count: int
    tests_present: bool
    has_docs: bool
    topics: list[str] = field(default_factory=list)
    excerpts: list[Excerpt] = field(default_factory=list)

    @property
    def short_sha(self) -> str:
        return self.sha[:8]

    def evidence_text(self) -> str:
        return "\n\n".join(f"=== [{e.ref}] ({e.kind}) ===\n{e.text}" for e in self.excerpts)

    def refs(self) -> set[str]:
        return {e.ref for e in self.excerpts}


def detect_license(text: str | None) -> str | None:
    if not text:
        return None
    for name, pat in LICENSE_PATTERNS:
        if re.search(pat, text, re.I):
            return name
    return None


def _score_source(path: str, keywords: list[str]) -> int:
    p = path.lower()
    return sum(3 for k in keywords if k in p) + (2 if "/src/" in f"/{p}" or p.startswith("src/") else 0) - p.count("/")


def inspect(project_json: dict, keywords: list[str] | None = None, budget_chars: int = 14000) -> RepoBundle | None:
    if project_json.get("provider") == "github":
        fn = project_json["full_name"]
        full = github.repo(fn) or project_json
        api = (lambda path, sha: github.raw_file(fn, path, sha))
        branch = full.get("default_branch")
        commit = github.head_commit(fn, branch) if branch else None
        if not commit:
            return None
        sha = commit["id"]
        items = [i for i in github.tree(fn, sha) if i["type"] == "blob"]
        lic_api = full.get("license_key") if full.get("license_key") not in (None, "noassertion") else None
        pid = project_json["id"]
    else:
        pid = project_json["id"]
        full = gitlab.project(pid) or project_json
        api = (lambda path, sha: gitlab.raw_file(pid, path, sha))
        branch = full.get("default_branch")
        if not branch:
            return None
        commit = gitlab.head_commit(pid, branch)
        if not commit:
            return None
        sha = commit["id"]
        items = [i for i in gitlab.tree(pid, sha) if i["type"] == "blob"]
        lic_api = (full.get("license") or {}).get("key") if full.get("license") else None
    paths = [i["path"] for i in items]
    keywords = [k.lower() for k in (keywords or []) if len(k) > 2]
    tests = [p for p in paths if re.search(r"(^|/)(tests?|spec|__tests__)/|_test\.|\.test\.|test_", p.lower())]
    b = RepoBundle(project_id=pid, name=full.get("name_with_namespace") or full["name"], web_url=full["web_url"],
                   description=full.get("description") or "", sha=sha, default_branch=branch, license_api=lic_api,
                   license_detected=None, stars=full.get("star_count", 0), last_activity=full.get("last_activity_at"),
                   file_count=len(paths), tests_present=bool(tests),
                   has_docs=any(p.lower().startswith("docs/") or p.lower().startswith("doc/") for p in paths),
                   topics=full.get("topics") or full.get("tag_list") or [])
    used = 0

    def add(path: str, kind: str, limit: int):
        nonlocal used
        if used >= budget_chars:
            return None
        txt = api(path, sha)
        if not txt:
            return None
        txt = txt[: min(limit, budget_chars - used)]
        used += len(txt)
        b.excerpts.append(Excerpt(ref=f"{path}@{b.short_sha}", kind=kind, text=txt))
        return txt

    b.excerpts.append(Excerpt(ref=f"api:project@{b.short_sha}", kind="metadata",
                              text=f"name={b.name}\ndescription={b.description}\nstars={b.stars}\n"
                                   f"last_activity={b.last_activity}\nlicense_api={lic_api}\ntopics={b.topics}\n"
                                   f"files={b.file_count} tests_present={b.tests_present}"))
    top = sorted({p.split("/")[0] + ("/" if "/" in p else "") for p in paths})[:60]
    b.excerpts.append(Excerpt(ref=f"tree@{b.short_sha}", kind="tree", text="\n".join(top)))
    readme = next((p for p in paths if re.fullmatch(r"readme(\.\w+)?", p.lower())), None)
    if readme:
        add(readme, "readme", 5000)
    lic = next((p for p in paths if re.fullmatch(r"(license|licence|copying)(\.\w+)?", p.lower())), None)
    if lic:
        t = add(lic, "license", 600)
        b.license_detected = detect_license(api(lic, sha))
    for m in [p for p in paths if p.split("/")[-1] in MANIFESTS and p.count("/") <= 1][:3]:
        add(m, "manifest", 1500)
    srcs = sorted([p for p in paths if p.endswith(SRC_EXT) and p not in tests], key=lambda p: -_score_source(p, keywords))
    for s in srcs[:3]:
        add(s, "source", 2000)
    for t in sorted(tests, key=lambda p: -_score_source(p, keywords))[:1]:
        add(t, "test", 1200)
    return b
