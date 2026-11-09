"""AR-01 requirement extraction and AR-02 capability modeling."""
from __future__ import annotations

import re

from pydantic import BaseModel

from shared import llm
from shared.schemas import Capability, OpenQuestion, Requirement

REQ_LINE = re.compile(r"\*\*(?P<id>[A-Z]{2}-[A-Z]{2,4}-\d{2})\*\*\s*(?P<text>.+)")


def parse_ids(srs_text: str) -> dict[str, str]:
    """Deterministic pass: requirement IDs explicitly present in the SRS."""
    return {m["id"]: m["text"].strip() for m in REQ_LINE.finditer(srs_text)}


class _Extraction(BaseModel):
    requirements: list[Requirement]
    open_questions: list[OpenQuestion]


EXTRACT_SYSTEM = """You are a senior systems engineer extracting requirements from a Software Requirements Specification.
Rules:
- Reuse the SRS requirement IDs exactly (e.g. SL-FT-01). Keep the requirement text faithful.
- kind: functional | nonfunctional | interface | constraint. priority: 'shall' -> mandatory, 'should' -> desirable, 'may' -> optional.
- status = explicit for numbered SRS statements. You may add a FEW inferred requirements (ids INF-01, INF-02, ...) only when clearly implied; mark status=inferred.
- source_passage: short quote from the SRS.
- ambiguity: set when the requirement is vague, unmeasurable, or conflicts with another; otherwise null.
- open_questions: one per missing numeric value, ambiguity, or contradiction (kind: missing_value | ambiguity | contradiction | scope). Ids OQ-01... NEVER invent numeric thresholds."""


def extract_requirements(srs_text: str) -> tuple[list[Requirement], list[OpenQuestion]]:
    out = llm.chat_json(EXTRACT_SYSTEM, f"SRS:\n{srs_text}", _Extraction, tag="e2:extract")
    reqs = {r.id: r for r in out.requirements}
    # Deterministic safety net: every numbered SRS statement must be present.
    for rid, text in parse_ids(srs_text).items():
        if rid not in reqs:
            prio = "mandatory" if " shall " in f" {text} " else "desirable"
            reqs[rid] = Requirement(id=rid, text=text, kind="functional", priority=prio, status="explicit",
                                    source_passage=text[:160], ambiguity="Recovered by parser; classification not reviewed")
    order = list(parse_ids(srs_text))
    ordered = sorted(reqs.values(), key=lambda r: (order.index(r.id) if r.id in order else 10_000, r.id))
    return ordered, out.open_questions


class _CapTree(BaseModel):
    capabilities: list[Capability]


CAP_SYSTEM = """You build a hierarchical capability model (domain -> capability -> operation) that is
independent of implementation components.
Rules:
- IDs are stable dotted uppercase: domain CAP.TRACK, capability CAP.TRACK.HISTORY, operation CAP.TRACK.HISTORY.PLAYBACK.
- Prefer these domain IDs where they fit: CAP.TRACK (friendly-force tracking), CAP.MAP, CAP.ROUTE, CAP.VIDEO, CAP.FUSION,
  CAP.DIARY, CAP.ALERT, CAP.DEVICE, CAP.COMMS, CAP.MOBILE, CAP.SEC, CAP.PLATFORM.
- Every capability/operation has parent_id; domains have parent_id null.
- Map each capability/operation to the requirement IDs it satisfies (requirement_ids). Every mandatory requirement must
  appear in at least one capability.
- Aim for 10-14 domains max, 25-45 capabilities+operations total. Short descriptions."""


def build_capability_tree(requirements: list[Requirement]) -> list[Capability]:
    lines = "\n".join(f"{r.id} [{r.priority}/{r.kind}] {r.text}" for r in requirements)
    out = llm.chat_json(CAP_SYSTEM, f"REQUIREMENTS:\n{lines}", _CapTree, tag="e2:captree")
    ids = {c.id for c in out.capabilities}
    for c in out.capabilities:          # repair dangling parents deterministically
        if c.parent_id and c.parent_id not in ids:
            c.parent_id = c.id.rsplit(".", 1)[0] if c.id.rsplit(".", 1)[0] in ids else None
    return out.capabilities
