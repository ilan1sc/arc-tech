"""Passport drafting (LLM) + deterministic post-processing that enforces evidence discipline."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from shared import judge, llm
from shared.schemas import (AdaptationEffortHours, ComponentSearchSpec, CostInputs, InterfaceDetail,
                            PassportCapability, PassportEvidence, PassportSource, PassportValidation,
                            SoftwareCapabilityPassport)

from .inspect_repo import RepoBundle

PERMISSIVE = {"mit", "apache-2.0", "bsd", "bsd-2-clause", "bsd-3-clause", "isc", "zlib", "unlicense", "mpl-2.0", "0bsd"}
WEAK_COPYLEFT = {"lgpl", "lgpl-2.1", "lgpl-3.0", "epl-2.0", "eupl", "eupl-1.2"}
STRONG_COPYLEFT = {"gpl", "gpl-2.0", "gpl-3.0", "agpl-3.0"}


class _CapDraft(BaseModel):
    name: str
    capability_id: Optional[str] = None
    coverage: Literal["full", "partial", "none"]
    evidence_status: Literal["verified", "declared", "inferred", "unknown"]
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str]
    notes: str


class _PassportDraft(BaseModel):
    description: str
    version: str
    capabilities: list[_CapDraft]
    interfaces_detail: list[InterfaceDetail]
    dependencies: list[str]
    runtime: list[str]
    deployment_constraints: list[str]
    maturity: Literal["experimental", "developing", "stable", "unknown"]
    adaptation_hours_estimate: float = Field(ge=0)
    adaptation_confidence: Literal["low", "medium", "high"]
    adaptation_assumptions: list[str]
    known_gaps: list[str]
    risks: list[str]
    evidence: list[PassportEvidence]


SYSTEM = """You write evidence-backed Software Capability Passports for a defense architecture team.
You see only a BOUNDED sample of the repository (metadata, tree, README, manifests, a few files). Never claim complete code comprehension.
Rules:
- capabilities: FIRST one entry per REQUESTED capability id (use capability_id exactly), with coverage full/partial/none for THIS repo;
  then up to 4 other notable capabilities (capability_id null).
- evidence_status: verified = seen in source/test code excerpt; declared = only README/docs/metadata claims it; inferred = you deduce it
  indirectly; unknown = no evidence. coverage 'none' with evidence_status 'unknown' when nothing indicates the capability.
- evidence_refs and evidence[].source_ref MUST be copied exactly from the [ref] labels of the excerpts (e.g. 'README.md@1a2b3c4d').
- interfaces_detail: only interfaces visible in evidence (REST API, CLI, library API, file formats, protocols). Otherwise none.
- version: from manifest/metadata if visible, else 'unknown'.
- deployment_constraints: e.g. 'requires internet map tiles', 'needs GPU', 'Linux container available' — only if evidenced; say so.
- adaptation_hours_estimate: rough indicative hours to adapt this repo to the component (NOT full project integration); confidence low unless strong evidence.
- known_gaps: requested functions not supported or not evidenced. risks: license, maintenance, security, maturity.
- Do not invent performance numbers, prices or APIs."""


def draft_passport(bundle: RepoBundle, spec: ComponentSearchSpec) -> SoftwareCapabilityPassport:
    req = "\n".join(f"- {cid}: {spec.capability_names.get(cid, cid)}" for cid in spec.required_capabilities)
    user = (f"COMPONENT: {spec.component_id} {spec.name}\nPURPOSE: {spec.purpose}\nREQUESTED CAPABILITIES:\n{req}\n"
            f"REQUIRED INTERFACES:\n" + "\n".join(f"- {i}" for i in spec.interfaces_required[:8]) +
            f"\n\nREPOSITORY: {bundle.name} {bundle.web_url} @ {bundle.sha}\n\nEXCERPTS:\n{bundle.evidence_text()}")
    d = llm.chat_json(SYSTEM, user, _PassportDraft, tag=f"e1:passport:{bundle.project_id}:{spec.component_id}", role="engine1")
    return finalize(bundle, d)


def license_class(lic: str) -> str:
    l = (lic or "").lower()
    if not l or l == "unknown":
        return "unknown"
    if l in STRONG_COPYLEFT or l.startswith("gpl") or l.startswith("agpl"):
        return "strong-copyleft"
    if l in WEAK_COPYLEFT or l.startswith("lgpl"):
        return "weak-copyleft"
    if l in PERMISSIVE or l.startswith("bsd") or l in ("mit", "apache-2.0"):
        return "permissive"
    return "other"


def finalize(b: RepoBundle, d: _PassportDraft) -> SoftwareCapabilityPassport:
    """Deterministic evidence discipline: unknown refs are dropped and claims are downgraded."""
    valid = b.refs()
    kind_of = {e.ref: e.kind for e in b.excerpts}
    caps = []
    for c in d.capabilities:
        refs = [r for r in c.evidence_refs if r in valid]
        status = c.evidence_status
        if not refs and status in ("verified", "declared"):
            status = "inferred"
        if status == "verified" and not any(kind_of.get(r) in ("source", "test") for r in refs):
            status = "declared"   # README/manifest is a declaration, not verification
        if c.coverage == "none":
            status = "unknown" if not refs else status
        caps.append(PassportCapability(name=c.name, capability_id=c.capability_id, coverage=c.coverage,
                                       evidence_status=status, confidence=c.confidence, evidence_refs=refs,
                                       notes=c.notes))
    evidence = []
    for e in d.evidence:
        ok = e.source_ref in valid
        path = e.source_ref.split("@")[0]
        if ok:
            ref = e.source_ref
        elif path in b.all_paths:      # file exists at this commit but was outside the bounded sample
            ref = f"NOT-INSPECTED:{path}@{b.short_sha}"
        else:                          # not in the repository at all -> fabricated citation
            ref = f"UNRESOLVED:{e.source_ref}"
        evidence.append(PassportEvidence(claim=e.claim, source_ref=ref, verified=ok and kind_of.get(e.source_ref) in ("source", "test")))
    lic = b.license_api or b.license_detected or "unknown"
    risks = list(d.risks)
    lc = license_class(lic)
    if lc == "unknown":
        risks.insert(0, "License unknown — must be verified before reuse")
    elif lc == "strong-copyleft":
        risks.insert(0, f"{lic}: strong copyleft, conflicts with closed redistribution (SL-DEP-02)")
    elif lc == "weak-copyleft":
        risks.insert(0, f"{lic}: weak copyleft, dynamic linking/legal review required")
    return SoftwareCapabilityPassport(
        passport_id=(f"PP-GH-{str(b.project_id)[3:].replace(chr(47), chr(95))}" if str(b.project_id).startswith("gh:") else f"PP-GL-{b.project_id}"), software_name=b.name, version=d.version or "unknown",
        source=PassportSource(repository_url=b.web_url, homepage_url=""),
        capabilities=caps, interfaces=[f"{i.name} ({i.protocol})" for i in d.interfaces_detail],
        interfaces_detail=d.interfaces_detail, dependencies=d.dependencies, license=lic, maturity=d.maturity,
        constraints=d.deployment_constraints, deployment_constraints=d.deployment_constraints, runtime=d.runtime,
        adaptation_effort_hours=AdaptationEffortHours(estimate=d.adaptation_hours_estimate,
                                                      confidence=d.adaptation_confidence,
                                                      assumptions=d.adaptation_assumptions + ["Indicative only; excludes project-level integration"]),
        evidence=evidence, validation=PassportValidation(status="pending"), revision=b.sha,
        description=d.description or b.description, tests_present=b.tests_present, known_gaps=d.known_gaps,
        risks=risks, cost_inputs=CostInputs(license_pricing_known=lc == "permissive",
                                            license_pricing_note="no license fee (open source)" if lc == "permissive" else "unknown",
                                            adaptation_assumptions=d.adaptation_assumptions),
        stars=b.stars, last_activity=b.last_activity)


def deterministic_checks(p: SoftwareCapabilityPassport, b: RepoBundle | None) -> tuple[list[str], list[str]]:
    fails, oks = [], []
    if not p.source.repository_url:
        fails.append("missing source link")
    else:
        oks.append("source link present")
    if b and p.revision != b.sha:
        fails.append("revision is not the inspected commit")
    elif p.revision:
        oks.append(f"pinned revision {p.revision[:8]}")
    if not any(c.coverage != "none" and c.evidence_refs for c in p.capabilities):
        fails.append("no traceable capability (needs >=1 capability with evidence refs)")
    else:
        oks.append("at least one traceable capability")
    unresolved = [e.source_ref for e in p.evidence if e.source_ref.startswith("UNRESOLVED:")]
    if unresolved:
        fails.append(f"citations to files that do not exist in the repository at this commit: {unresolved[:3]}")
    not_inspected = [e.source_ref for e in p.evidence if e.source_ref.startswith("NOT-INSPECTED:")]
    if not_inspected:
        oks.append(f"cited files exist but were outside the bounded sample (unverified): {not_inspected[:3]}")
    if p.license == "unknown":
        oks.append("license explicitly marked unknown")
    return fails, oks


def validate_passport(p: SoftwareCapabilityPassport, b: RepoBundle | None) -> SoftwareCapabilityPassport:
    fails, oks = deterministic_checks(p, b)
    rep = judge.judge("passport", p.passport_id, p.model_dump(exclude={"validation"}),
                      evidence=b.evidence_text() if b else "", deterministic_failures=fails, deterministic_passes=oks)
    p.validation = PassportValidation(
        status={"PASS": "passed", "REVISE": "pending", "BLOCK": "failed"}[rep.verdict],
        judge_notes=f"{rep.verdict}: " + " | ".join(f"[{f.severity}] {f.problem}" for f in rep.findings[:5]))
    return p


def custom_development_candidate(spec: ComponentSearchSpec) -> SoftwareCapabilityPassport:
    """Baseline candidate when nothing matches: build it in-house."""
    return SoftwareCapabilityPassport(
        passport_id=f"PP-CUSTOM-{spec.component_id}", software_name=f"Custom development: {spec.name}",
        version="n/a", source=PassportSource(),
        capabilities=[PassportCapability(name=spec.capability_names.get(c, c), capability_id=c, coverage="full",
                                         evidence_status="inferred", confidence=0.5,
                                         notes="Built to specification; coverage assumed by design")
                      for c in spec.required_capabilities],
        interfaces=["As specified by Engine 2"], license="proprietary (in-house)", maturity="unknown",
        adaptation_effort_hours=AdaptationEffortHours(estimate=0, confidence="low",
                                                      assumptions=["Build effort estimated by Engine 3, not here"]),
        evidence=[], validation=PassportValidation(status="passed", judge_notes="Synthetic BUILD baseline; no external claims"),
        is_custom_development=True, cost_inputs=CostInputs(license_pricing_known=True, license_pricing_note="no license fee"),
        description="Represents in-house development when no reusable candidate covers the component.")
