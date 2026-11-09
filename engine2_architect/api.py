"""Engine 2 public contract (independently callable by Engine 3).

generate_architecture({srs_text, constraints?, glossary?}) -> ArchitectureDesign
get_component_requirements({architecture_id}) -> ComponentSearchSpec[]
revise_architecture({architecture_id, feedback, changed_requirements?}) -> ArchitectureDesign
"""
from __future__ import annotations

import hashlib
from typing import Optional

from shared import store
from shared.schemas import (ArchitectureDesign, ArchitectureFeedback, ChangeLogEntry, ComponentSearchSpec)

from . import mermaid
from .extract import build_capability_tree, extract_requirements
from .synthesize import ArchDraft, revise, synthesize
from .validate import compute_coverage, validate

KIND = "architecture"


def _assemble(draft: ArchDraft, base: dict) -> ArchitectureDesign:
    d = ArchitectureDesign(**base, title=draft.title, design_rationale=draft.design_rationale,
                           components=draft.components, interfaces=draft.interfaces, data_stores=draft.data_stores,
                           external_systems=draft.external_systems, assumptions=draft.assumptions, risks=draft.risks)
    d.coverage = compute_coverage(d)
    d.validation_findings = validate(d)
    d.mermaid_source = mermaid.render(d)
    return d


def generate_architecture(srs_text: str, constraints: Optional[list[str]] = None,
                          glossary: Optional[str] = None, architecture_id: str = "ARCH-SWISSLINK") -> ArchitectureDesign:
    srs = srs_text + (f"\n\nGLOSSARY:\n{glossary}" if glossary else "")
    requirements, questions = extract_requirements(srs)
    capabilities = build_capability_tree(requirements)
    draft = synthesize(requirements, capabilities, constraints or [], questions)
    base = dict(architecture_id=architecture_id, version=1,
                requirements_revision=hashlib.sha256(srs.encode()).hexdigest()[:12],
                requirements=requirements, open_questions=questions, capabilities=capabilities,
                constraints=constraints or [],
                change_log=[ChangeLogEntry(version=1, summary="Initial architecture generated from SRS")])
    d = _assemble(draft, base)
    gaps = [c.requirement_id for c in d.coverage if c.status == "gap"
            and next(r for r in d.requirements if r.id == c.requirement_id).priority == "mandatory"]
    if gaps:   # AR-03 completeness: one bounded repair pass before publishing v1
        texts = {r.id: r.text for r in d.requirements}
        fb = ArchitectureFeedback(feedback_id="FB-SELFCHECK", requested_change=(
            "Allocate these unallocated mandatory requirements to existing or new components (add requirement_ids and "
            "capabilities; add a component if responsibility is missing): " + "; ".join(f"{g}: {texts[g]}" for g in gaps)),
            observations=["Engine 2 deterministic validation found unallocated mandatory requirements"], priority="high")
        draft = revise(d, fb, [])
        d = _assemble(draft, base)
        d.change_log.append(ChangeLogEntry(version=1, summary=f"Self-check repair pass allocated: {', '.join(gaps)}",
                                           reason="AR-06 validation before first publication"))
    store.save(KIND, architecture_id, d, version=1)
    return d


def get_architecture(architecture_id: str, version: Optional[int] = None) -> Optional[ArchitectureDesign]:
    return store.load(KIND, architecture_id, ArchitectureDesign, version)


def list_versions(architecture_id: str) -> list[int]:
    return store.versions(KIND, architecture_id)


def get_component_requirements(architecture_id: str, version: Optional[int] = None) -> list[ComponentSearchSpec]:
    d = get_architecture(architecture_id, version)
    if d is None:
        raise KeyError(architecture_id)
    cap_names = {c.id: c.name for c in d.capabilities}
    req = {r.id: r for r in d.requirements}
    sec = [r.text for r in d.requirements if r.kind == "constraint" or r.id.startswith("SL-SEC") or r.id.startswith("SL-DEP")]
    specs = []
    for c in d.components:
        itfs = [f"{i.name} ({'out' if i.source == c.id else 'in'}; {', '.join(i.protocol_candidates) or 'protocol TBD'})"
                for i in d.interfaces if c.id in (i.source, i.target)]
        terms = list(dict.fromkeys([cap_names.get(x, x) for x in c.required_capabilities][:4]))
        specs.append(ComponentSearchSpec(
            component_id=c.id, name=c.name, purpose=c.purpose,
            required_capabilities=c.required_capabilities, optional_capabilities=c.optional_capabilities,
            capability_names={x: cap_names.get(x, x) for x in c.required_capabilities + c.optional_capabilities},
            interfaces_required=itfs, data_constraints=c.data_owned,
            runtime_constraints=c.runtime_assumptions + c.deployment_assumptions + d.constraints,
            security_constraints=sec, requirement_ids=c.requirement_ids,
            acceptance_criteria=[f"{rid}: {req[rid].text}" for rid in c.requirement_ids if rid in req],
            search_terms=terms))
    return specs


def diff(old: ArchitectureDesign, new: ArchitectureDesign) -> dict:
    def index(d):
        return {**{c.id: c.model_dump() for c in d.components},
                **{i.id: i.model_dump() for i in d.interfaces},
                **{s.id: s.model_dump() for s in d.data_stores},
                **{e.id: e.model_dump() for e in d.external_systems}}
    a, b = index(old), index(new)
    modified = []
    for k in a.keys() & b.keys():
        if a[k] != b[k]:
            fields = [f for f in a[k] if a[k].get(f) != b[k].get(f)]
            modified.append({"id": k, "fields": fields})
    cov_old = {c.requirement_id: c.status for c in old.coverage}
    cov_new = {c.requirement_id: c.status for c in new.coverage}
    return {"added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
            "modified": sorted(modified, key=lambda m: m["id"]),
            "coverage_changes": {k: f"{cov_old.get(k)} -> {v}" for k, v in cov_new.items() if cov_old.get(k) != v},
            "gaps_before": sum(1 for v in cov_old.values() if v == "gap"),
            "gaps_after": sum(1 for v in cov_new.values() if v == "gap")}


def revise_architecture(architecture_id: str, feedback: ArchitectureFeedback,
                        changed_requirements: Optional[list[str]] = None,
                        from_version: Optional[int] = None) -> ArchitectureDesign:
    old = get_architecture(architecture_id, from_version)
    if old is None:
        raise KeyError(architecture_id)
    extra = feedback.changed_constraints + (changed_requirements or [])
    draft = revise(old, feedback, extra)
    new_version = max(list_versions(architecture_id) or [old.version]) + 1
    base = dict(architecture_id=architecture_id, version=new_version, parent_id=old.key,
                requirements_revision=old.requirements_revision, requirements=old.requirements,
                open_questions=old.open_questions, capabilities=old.capabilities,
                constraints=list(dict.fromkeys(old.constraints + extra)), change_log=list(old.change_log))
    new = _assemble(draft, base)
    dd = diff(old, new)
    new.change_log.append(ChangeLogEntry(
        version=new_version, summary=feedback.requested_change, reason="; ".join(feedback.observations)[:500],
        added=dd["added"], removed=dd["removed"], modified=[m["id"] for m in dd["modified"]],
        feedback_id=feedback.feedback_id))
    store.save(KIND, architecture_id, new, version=new_version)
    return new
