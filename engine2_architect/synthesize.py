"""AR-03/04/05 architecture synthesis and AR-09 controlled revision."""
from __future__ import annotations

import json

from pydantic import BaseModel

from shared import llm
from shared.schemas import (ArchitectureDesign, ArchitectureFeedback, Capability, Component, DataStore,
                            ExternalSystem, Interface, OpenQuestion, Requirement)


class ArchDraft(BaseModel):
    title: str
    design_rationale: str
    components: list[Component]
    interfaces: list[Interface]
    data_stores: list[DataStore]
    external_systems: list[ExternalSystem]
    assumptions: list[str]
    risks: list[str]


SYNTH_SYSTEM = """You are a principal software architect. Produce ONE coherent, technically justified LOGICAL architecture.
Rules:
- Cover the full scope. Every mandatory requirement must be allocated (component.requirement_ids).
- Choose patterns on engineering grounds; avoid gratuitous microservices. Typically 12-18 components.
- Components are implementation-neutral: NEVER name a product, vendor, library or open-source project.
- Component ids: short stable uppercase 'C-<WORD>' (e.g. C-TRACK, C-MAP-UI). Interface ids 'IF-01'... Data store ids 'DS-<WORD>'.
  External system ids 'X-<WORD>' (fictional devices: fictional=true).
- subsystem groups components (e.g. 'Field edge', 'Command post core', 'Video analytics', 'Clients').
- trust_zone e.g. 'field', 'command-post', 'mobile'.
- required_capabilities use capability ids from the given capability tree only.
- interfaces: directed source->target among component/external/data-store ids; payload is a short example or schema sketch;
  protocol_candidates are generic (e.g. 'pub/sub topic', 'REST', 'gRPC', 'RTSP-like video stream'); include error_handling and security.
- data_stores: owner_component must be a component id.
- Separate required properties from design_assumptions. Do not invent numeric thresholds: if the SRS lacks a number, say 'TBD (open question)'.
- design_rationale: 5-8 sentences explaining the key structural choices.
Return JSON only."""


def _context(requirements: list[Requirement], capabilities: list[Capability], constraints: list[str],
             questions: list[OpenQuestion]) -> str:
    reqs = "\n".join(f"{r.id} [{r.priority}] {r.text}" for r in requirements)
    caps = "\n".join(f"{c.id} ({c.level}) {c.name} <- {','.join(c.requirement_ids)}" for c in capabilities)
    oq = "\n".join(f"{q.id}: {q.question}" for q in questions)
    cons = "\n".join(f"- {c}" for c in constraints) or "(none beyond SRS)"
    return f"REQUIREMENTS:\n{reqs}\n\nCAPABILITY TREE:\n{caps}\n\nOPEN QUESTIONS:\n{oq}\n\nADDITIONAL CONSTRAINTS:\n{cons}"


def synthesize(requirements, capabilities, constraints, questions) -> ArchDraft:
    return llm.chat_json(SYNTH_SYSTEM, _context(requirements, capabilities, constraints, questions), ArchDraft,
                         tag="e2:synth", temperature=0.2)


REVISE_SYSTEM = SYNTH_SYSTEM + """

REVISION MODE: You receive the CURRENT architecture and an explicit change request from the optimizer (PRD 3).
- Change only what the request requires. KEEP ids of unchanged components/interfaces/data stores EXACTLY.
- New entities get new ids; removed entities simply disappear.
- Do not produce alternatives or rank designs; return the single revised architecture."""


def revise(design: ArchitectureDesign, feedback: ArchitectureFeedback, extra_constraints: list[str]) -> ArchDraft:
    current = ArchDraft(title=design.title, design_rationale=design.design_rationale, components=design.components,
                        interfaces=design.interfaces, data_stores=design.data_stores,
                        external_systems=design.external_systems, assumptions=design.assumptions, risks=design.risks)
    user = (_context(design.requirements, design.capabilities, design.constraints + extra_constraints, design.open_questions)
            + f"\n\nCURRENT ARCHITECTURE JSON:\n{current.model_dump_json()}"
            + f"\n\nCHANGE REQUEST (from PRD 3):\n{json.dumps(feedback.model_dump(), indent=1)}")
    return llm.chat_json(REVISE_SYSTEM, user, ArchDraft, tag=f"e2:revise:{feedback.feedback_id}", temperature=0.1)
