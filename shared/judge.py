"""Independent LLM judge (one shared service, engine-specific rubrics).

Deterministic checks run first; any critical deterministic failure forces BLOCK
regardless of what the LLM says.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from . import llm
from .schemas import JudgeFinding, ValidationReport

RUBRICS = {
    "passport": """You audit a Software Capability Passport against the cited evidence excerpts.
- evidence_status meanings: verified = seen in source/test code; declared = stated by README/docs/metadata (README evidence is
  SUFFICIENT for 'declared' - do not demand code for declared); inferred = indirect; unknown = no evidence.
- Flag a capability whose cited excerpt does not actually support its coverage level, and any 'verified' without code/test evidence.
- Citations marked NOT-INSPECTED exist in the repo but were not read: treat their claims as unverified (medium), not fabricated.
- Citations marked UNRESOLVED do not exist in the repo: that is fabrication (critical).
- License, interfaces, performance claims not present in the evidence must be 'unknown'.
- Flag invented numbers, invented APIs, or overstated maturity.""",
    "ranking": """You audit a ranking of candidate software for one architecture component.
- Scores must follow from the passports and the stated weights; flag scores without evidence.
- Hard-gate exclusions must cite a concrete reason.
- Unknown must not be treated as unsupported or as zero.""",
    "architecture": """You audit a logical software architecture generated from an SRS.
- Every mandatory requirement must be allocated to a component or explicitly listed as a gap.
- Flag invented numeric thresholds not present in the SRS.
- Flag components that name a specific vendor/product (must be implementation-neutral).
- Flag interfaces whose endpoints, payloads or security are inconsistent.""",
    "evaluation": """You audit a Build/Buy/Reuse evaluation with effort hours and money.
- Hours/money must state assumptions; missing estimates must be unknown, not zero.
- Flag double counting of shared integration work.
- Flag any claim that integration is verified, or any single 'winner' claim based on false precision.""",
}

SYSTEM = """You are an independent, skeptical technical reviewer for a defense software architecture team.
Only judge using the artifact and the evidence given. Do not use outside knowledge to fill gaps.
Verdict: PASS (no material issues), REVISE (fixable issues), BLOCK (critical unsupported claim or broken constraint).
Return at most 8 findings, most severe first. Be concrete: quote the claim and say what evidence is missing."""


class _JudgeOut(BaseModel):
    verdict: Literal["PASS", "REVISE", "BLOCK"]
    findings: list[JudgeFinding]


def judge(target_kind: str, target_id: str, artifact: dict | str, evidence: str = "",
          deterministic_failures: list[str] | None = None,
          deterministic_passes: list[str] | None = None) -> ValidationReport:
    deterministic_failures = deterministic_failures or []
    checks = [f"FAIL: {m}" for m in deterministic_failures] + [f"ok: {m}" for m in (deterministic_passes or [])]
    art = artifact if isinstance(artifact, str) else json.dumps(artifact, indent=1)[:24000]
    user = (f"RUBRIC:\n{RUBRICS[target_kind]}\n\nARTIFACT ({target_kind} {target_id}):\n{art}\n\n"
            f"EVIDENCE EXCERPTS:\n{evidence[:20000] or '(none supplied)'}\n\n"
            f"DETERMINISTIC CHECK RESULTS:\n" + ("\n".join(checks) or "(none)"))
    try:
        out = llm.chat_json(SYSTEM, user, _JudgeOut, role="judge", temperature=0.0, tag=f"judge:{target_id}")
        verdict, findings = out.verdict, out.findings
    except llm.LLMUnavailable as e:
        verdict, findings = "REVISE", [JudgeFinding(severity="medium", claim="(judge)", problem=f"LLM judge unavailable: {e}")]
    if deterministic_failures:
        verdict = "BLOCK"
        findings = [JudgeFinding(severity="critical", claim="deterministic check", problem=m) for m in deterministic_failures] + findings
    return ValidationReport(target_kind=target_kind, target_id=target_id, verdict=verdict, findings=findings,
                            deterministic_checks=checks, rubric=RUBRICS[target_kind], model=llm.model_for("judge"))
