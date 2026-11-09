"""Engine 1 public contract.

search_terms(spec) -> list[str]                        (LLM, only capability words; nothing internal leaves the box)
discover(spec, ...) -> list[project json]              (public GitLab search, dedup, relevance-ranked)
explore_component(spec, ...) -> ExplorationResult      (inspect -> passport -> judge -> rank, + custom-dev candidate)
"""
from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel

from shared import llm, store
from shared.schemas import CandidateRanking, ComponentSearchSpec, SoftwareCapabilityPassport

from . import github, gitlab
from .inspect_repo import inspect
from .passport import custom_development_candidate, draft_passport, validate_passport
from .rank import rank_component, verify_arithmetic


class _Terms(BaseModel):
    queries: list[str]


class ExplorationResult(BaseModel):
    component_id: str
    queries: list[str]
    discovered: list[dict]          # lightweight GitLab hits (all, after dedup)
    passports: list[SoftwareCapabilityPassport]
    rankings: list[CandidateRanking]
    errors: list[str] = []

    def shortlist(self, n: int = 5) -> list[CandidateRanking]:
        return [r for r in self.rankings if r.eligible and r.rank][:n]


TERMS_SYSTEM = """Generate 3 short public GitHub/GitLab repository search queries (1-3 words each, English, generic technical terms,
no product names unless they are very well-known open-source categories) that would find open-source software
providing the requested capabilities. Return JSON {"queries": [...]}"""


def search_terms(spec: ComponentSearchSpec) -> list[str]:
    caps = ", ".join(spec.capability_names.values())
    try:
        q = llm.chat_json(TERMS_SYSTEM, f"Component: {spec.name}\nCapabilities: {caps}", _Terms,
                          tag=f"e1:terms:{spec.component_id}").queries
    except llm.LLMUnavailable:
        q = []
    return list(dict.fromkeys([t.lower().strip() for t in q + spec.search_terms if t.strip()]))[:4]


def discover(spec: ComponentSearchSpec, queries: list[str], per_query: int = 8, keep: int = 5,
             providers: tuple[str, ...] = ("github", "gitlab")) -> list[dict]:
    """Search public GitHub + GitLab, dedupe, rank by semantic relevance (+ small popularity term)."""
    hits: dict = {}
    for q in queries:
        if "gitlab" in providers:
            try:
                for p in gitlab.search_projects(q, per_page=per_query):
                    p = {k: p.get(k) for k in ("id", "name", "name_with_namespace", "description", "web_url", "star_count",
                                               "last_activity_at", "default_branch", "topics")}
                    p["provider"] = "gitlab"
                    p["matched_query"] = q
                    hits.setdefault(f"gl:{p['id']}", p)
            except gitlab.GitLabUnavailable:
                pass
        if "github" in providers:
            try:
                for p in github.search_repos(q, per_page=per_query):
                    p["matched_query"] = q
                    hits.setdefault(p["id"], p)
            except github.GitHubUnavailable:
                pass
    hits_l = [h for h in hits.values() if h.get("default_branch")]
    if not hits_l:
        return []
    try:   # semantic relevance of description to the component purpose
        texts = [f"{spec.name}. {spec.purpose}. " + ", ".join(spec.capability_names.values())] + \
                [f"{h['name']}. {h.get('description') or ''}" for h in hits_l]
        vecs = llm.embed(texts)
        for h, v in zip(hits_l, vecs[1:]):
            h["relevance"] = round(llm.cosine(vecs[0], v), 3)
    except Exception:  # noqa: BLE001
        for h in hits_l:
            h["relevance"] = None
    import math
    hits_l.sort(key=lambda h: -((h["relevance"] or 0) + 0.03 * math.log1p(h.get("star_count") or 0)))
    for i, h in enumerate(hits_l):
        h["selected"] = i < keep
    return hits_l


def explore_component(spec: ComponentSearchSpec, *, queries: Optional[list[str]] = None, keep: int = 3,
                      weights: Optional[dict] = None, validate: bool = True,
                      progress: Callable[[str], None] = lambda m: None) -> ExplorationResult:
    errors: list[str] = []
    queries = queries or search_terms(spec)
    progress(f"Searching GitHub + GitLab: {queries}")
    try:
        hits = discover(spec, queries, keep=keep)
    except (gitlab.GitLabUnavailable, github.GitHubUnavailable) as e:
        hits, errors = [], [f"Repository search unavailable: {e}"]
    passports: list[SoftwareCapabilityPassport] = []
    keywords = [w for q in queries for w in q.split()]
    for h in [h for h in hits if h.get("selected")]:
        try:
            progress(f"Inspecting {h['name_with_namespace']}")
            bundle = inspect(h, keywords)
            if bundle is None:
                errors.append(f"{h['web_url']}: empty repository")
                continue
            progress(f"Drafting passport for {bundle.name} @ {bundle.short_sha}")
            p = draft_passport(bundle, spec)
            if validate:
                progress(f"Independent judge reviewing {p.passport_id}")
                p = validate_passport(p, bundle)
            store.save("passport", p.passport_id, p)
            passports.append(p)
        except (gitlab.GitLabUnavailable, github.GitHubUnavailable, llm.LLMUnavailable) as e:
            errors.append(f"{h['web_url']}: {e}")
    passports.append(custom_development_candidate(spec))
    rankings = rank_component(spec, passports, weights)
    bad = [r.candidate_id for r in rankings if not verify_arithmetic(r)]
    if bad:
        errors.append(f"score arithmetic check failed for {bad}")
    res = ExplorationResult(component_id=spec.component_id, queries=queries, discovered=hits,
                            passports=passports, rankings=rankings, errors=errors)
    store.save("exploration", spec.component_id, res)
    return res


def load_exploration(component_id: str) -> Optional[ExplorationResult]:
    return store.load("exploration", component_id, ExplorationResult)


def adhoc_spec(query: str, capabilities: dict[str, str], component_id: str = "ADHOC") -> ComponentSearchSpec:
    return ComponentSearchSpec(component_id=component_id, name=query, purpose=query,
                               required_capabilities=list(capabilities), capability_names=capabilities,
                               search_terms=[query])
