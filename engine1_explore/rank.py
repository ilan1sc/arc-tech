"""Software Suitability Ranking (PRD 1 v0.3): hard gates first, then editable weighted dimensions.

Engine 1 ranks component FIT only; Engine 3 chooses Build/Buy/Reuse.
Unknown dimensions are excluded from the weighted mean (and lower confidence) - never scored as 0.
"""
from __future__ import annotations

from typing import Optional

from shared.schemas import CandidateRanking, ComponentSearchSpec, SoftwareCapabilityPassport

from .passport import license_class

DEFAULT_WEIGHTS = {
    "functional_coverage": 0.35,
    "interface_fit": 0.15,
    "adaptation_effort": 0.15,
    "maturity": 0.15,
    "documentation": 0.10,
    "operational_fit": 0.10,
}
COV = {"full": 1.0, "partial": 0.5, "none": 0.0}
MATURITY = {"stable": 1.0, "developing": 0.6, "experimental": 0.3}
CLOUD_WORDS = ("internet", "cloud", "online", "saas", "google maps", "api key", "hosted")


def offline_required(spec: ComponentSearchSpec) -> bool:
    text = " ".join(spec.runtime_constraints + spec.security_constraints).lower()
    return "offline" in text or "on-premises" in text or "no data may be sent to public cloud" in text


def _cap_coverage(p: SoftwareCapabilityPassport, cap_id: str) -> Optional[str]:
    for c in p.capabilities:
        if c.capability_id == cap_id:
            return c.coverage
    return None


def rank_component(spec: ComponentSearchSpec, passports: list[SoftwareCapabilityPassport],
                   weights: Optional[dict[str, float]] = None, gates: Optional[dict[str, bool]] = None) -> list[CandidateRanking]:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    gates = {"mandatory_capability": True, "license": True, "offline": True, "judge_block": True, **(gates or {})}
    needs_offline = offline_required(spec)
    real = [p for p in passports if not p.is_custom_development]
    max_h = max([p.adaptation_effort_hours.estimate for p in real] + [1.0])
    out: list[CandidateRanking] = []
    for p in passports:
        reasons, mods = [], []
        covs = {cid: _cap_coverage(p, cid) for cid in spec.required_capabilities}
        covered = [c for c, v in covs.items() if v in ("full", "partial")]
        missing = [c for c, v in covs.items() if v in (None, "none")]
        lc = license_class(p.license) if not p.is_custom_development else "permissive"
        # ---- hard gates (excluded candidates keep a visible reason) ----
        if gates["mandatory_capability"] and spec.required_capabilities and not covered:
            reasons.append("Covers none of the mandatory capabilities")
        if gates["license"] and lc == "strong-copyleft":
            reasons.append(f"License {p.license} incompatible with closed redistribution (SL-DEP-02)")
        if gates["offline"] and needs_offline and any(any(w in c.lower() for w in CLOUD_WORDS) for c in p.deployment_constraints):
            reasons.append("Requires online/cloud service but component must run on-premises/offline")
        if gates["judge_block"] and p.validation.status == "failed":
            reasons.append("Blocked by independent validation: " + p.validation.judge_notes[:160])
        # ---- dimensions (0..1, None = unknown) ----
        dims: dict[str, Optional[float]] = {}
        dims["functional_coverage"] = (sum(COV.get(covs[c] or "none", 0) for c in covs) / len(covs)) if covs else None
        if p.is_custom_development:
            dims["interface_fit"] = 1.0
            dims["adaptation_effort"] = None
            dims["maturity"] = None
            dims["documentation"] = None
            dims["operational_fit"] = 1.0
        else:
            known_itf = [i for i in p.interfaces_detail if i.protocol != "unknown"]
            dims["interface_fit"] = min(1.0, len(known_itf) / max(1, min(3, len(spec.interfaces_required)))) if p.interfaces_detail else None
            dims["adaptation_effort"] = 1 - p.adaptation_effort_hours.estimate / (max_h * 1.25) if max_h else None
            dims["maturity"] = MATURITY.get(p.maturity)
            readme = any(r.startswith("README") or "readme" in r.lower() for c in p.capabilities for r in c.evidence_refs) or bool(p.description)
            dims["documentation"] = (0.5 if readme else 0.2) + (0.3 if p.tests_present else 0) + (0.2 if p.interfaces_detail else 0)
            dims["operational_fit"] = None if not (p.deployment_constraints or p.runtime) else (
                0.3 if any(any(w in c.lower() for w in CLOUD_WORDS) for c in p.deployment_constraints) else 0.9)
        if lc in ("unknown", "weak-copyleft", "other"):
            mods.append(f"Legal review of license '{p.license}'")
        mods += [f"Implement/extend: {spec.capability_names.get(m, m)}" for m in missing]
        known = {k: v for k, v in dims.items() if v is not None}
        wsum = sum(weights[k] for k in known)
        total = round(100 * sum(weights[k] * v for k, v in known.items()) / wsum, 1) if wsum else None
        unknown_share = 1 - wsum / sum(weights.values())
        conf = "high" if unknown_share < 0.1 and p.validation.status == "passed" else "medium" if unknown_share < 0.35 else "low"
        expl = (f"{len(covered)}/{len(covs)} required capabilities covered"
                + (f"; missing {', '.join(spec.capability_names.get(m, m) for m in missing)}" if missing else "")
                + f"; license {p.license} ({lc}); maturity {p.maturity}"
                + (f"; unknown: {', '.join(k for k, v in dims.items() if v is None)}" if len(known) < len(dims) else ""))
        out.append(CandidateRanking(component_id=spec.component_id, candidate_id=p.passport_id, eligible=not reasons,
                                    exclusion_reasons=reasons, dimension_scores={k: (round(v, 3) if v is not None else None) for k, v in dims.items()},
                                    weights=weights, total_score=total if not reasons else None,
                                    covered_capabilities=covered, missing_capabilities=missing,
                                    required_modifications=mods, explanation=expl, confidence=conf))
    custom = [r for r in out if r.candidate_id.startswith("PP-CUSTOM")]
    for r in custom:   # BUILD baseline: shown for comparison, never scored against real candidates
        r.total_score, r.rank = None, None
        r.explanation = "BUILD baseline (custom development to specification). Not scored; Engine 3 estimates its effort."
    eligible = sorted([r for r in out if r.eligible and r not in custom], key=lambda r: -(r.total_score or 0))
    for i, r in enumerate(eligible, 1):
        r.rank = i
    return eligible + custom + [r for r in out if not r.eligible and r not in custom]


def verify_arithmetic(r: CandidateRanking) -> bool:
    """Deterministic check that total_score equals the weighted mean of known dimensions."""
    if not r.eligible or r.total_score is None:
        return True
    known = {k: v for k, v in r.dimension_scores.items() if v is not None}
    w = sum(r.weights[k] for k in known)
    return abs(100 * sum(r.weights[k] * v for k, v in known.items()) / w - r.total_score) < 0.2
