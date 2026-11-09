"""Engine 3 orchestration: drives Engine 2 (top-down) and Engine 1 (bottom-up) in an iterative conversation."""
from __future__ import annotations

import uuid
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from engine1_explore import api as e1
from engine1_explore.rank import rank_component
from engine2_architect import api as e2
from shared import llm, store
from shared.schemas import (ArchitectureDesign, ArchitectureEvaluation, ArchitectureFeedback, Iteration)

from .effort import EffortAssumptions
from .evaluate import STRATEGIES, Inputs, choose, evaluate, pareto

Progress = Callable[[str], None]
LABELS = {"balanced": "A · Balanced", "max_reuse": "B · Max reuse", "build_heavy": "C · Build-heavy"}


# ------------------------------------------------------------------ inputs
def gather(design: ArchitectureDesign, explore_missing: bool = False, keep: int = 2,
           progress: Progress = lambda m: None) -> Inputs:
    rankings, passports = {}, {}
    for spec in e2.get_component_requirements(design.architecture_id, design.version):
        res = e1.load_exploration(spec.component_id)
        stale = res is not None and set(spec.required_capabilities) != {c for r in res.rankings for c in (r.covered_capabilities + r.missing_capabilities)} and bool(spec.required_capabilities)
        if (res is None or stale) and explore_missing:
            progress(f"Engine 1 exploring {spec.component_id} {spec.name}")
            res = e1.explore_component(spec, keep=keep, progress=progress)
        if res is None:
            continue
        rankings[spec.component_id] = rank_component(spec, res.passports)   # always re-rank with current rules
        passports.update({p.passport_id: p for p in res.passports})
    return Inputs(design, rankings, passports)


def evaluate_all(design: ArchitectureDesign, a: EffortAssumptions, constraints: list[str],
                 strategies: Optional[list[str]] = None, progress: Progress = lambda m: None,
                 explore_missing: bool = False) -> list[ArchitectureEvaluation]:
    inp = gather(design, explore_missing=explore_missing, progress=progress)
    evals = []
    for s in strategies or list(STRATEGIES):
        opts = choose(inp, s, a, constraints)
        evals.append(evaluate(inp, opts, a, f"{LABELS[s]} ({design.key})", s, constraints))
    pareto(evals)
    return evals


# ------------------------------------------------------------------ conversation
class Intent(BaseModel):
    constraints: list[str]
    objectives: list[str]
    preferred_strategy: Literal["balanced", "max_reuse", "build_heavy", "none"]
    needs_architecture_revision: bool
    revision_request: str
    affected_components: list[str]
    explanation: str


INTENT_SYSTEM = """You translate an architect's natural-language instruction into explicit optimization inputs.
- constraints: hard gates (e.g. 'offline-only: no internet or cloud dependency at runtime').
- objectives: soft goals (e.g. 'minimize total engineering hours', 'maximize reuse of existing software').
- preferred_strategy: max_reuse for reuse/cost-cutting via reuse, build_heavy for control/minimal external dependency, balanced otherwise.
- needs_architecture_revision: true ONLY if the structure must change (new constraint affects components/interfaces, e.g. offline-only,
  remove a device, add a capability). Pure cost/reuse preferences do NOT need a revision.
- revision_request: precise change request for the architecture engine if revision is needed, else ''.
- affected_components: component ids from the list that are affected.
Never invent numbers."""


def parse_intent(text: str, design: ArchitectureDesign) -> Intent:
    comps = "\n".join(f"{c.id}: {c.name}" for c in design.components)
    try:
        return llm.chat_json(INTENT_SYSTEM, f"COMPONENTS:\n{comps}\n\nINSTRUCTION: {text}", Intent, tag="e3:intent")
    except llm.LLMUnavailable:
        t = text.lower()
        off = "offline" in t
        return Intent(constraints=["offline-only: no internet or cloud dependency at runtime"] if off else [],
                      objectives=(["maximize reuse of existing software"] if "reuse" in t else []) +
                                 (["minimize total engineering hours"] if any(w in t for w in ("cost", "cheap", "expensive", "hours")) else []),
                      preferred_strategy="max_reuse" if ("reuse" in t or "expensive" in t or "cost" in t) else "balanced",
                      needs_architecture_revision=off, revision_request="Make every component operate fully offline" if off else "",
                      affected_components=[], explanation="Keyword fallback (LLM unavailable)")


def new_iteration_id() -> str:
    return "IT-" + uuid.uuid4().hex[:6].upper()


def start(srs_text: str, a: EffortAssumptions, progress: Progress = lambda m: None,
          explore: bool = True) -> Iteration:
    design = e2.get_architecture("ARCH-SWISSLINK")
    if design is None:
        progress("Engine 2 generating architecture from SRS")
        design = e2.generate_architecture(srs_text)
    evals = evaluate_all(design, a, [], progress=progress, explore_missing=explore)
    it = Iteration(iteration_id=new_iteration_id(), user_instruction="Initial evaluation of SwissLink SRS",
                   proposals=[design.key], evaluations=evals,
                   explanation="Three Build/Buy/Reuse strategies evaluated on the Engine 2 architecture.",
                   changes=[f"{design.key}: {len(design.components)} components, {len(design.interfaces)} interfaces"])
    store.save("iteration", it.iteration_id, it)
    _index_add(it)
    return it


def refine(parent: Iteration, instruction: str, a: EffortAssumptions, progress: Progress = lambda m: None) -> Iteration:
    key = parent.proposals[-1]
    arch_id, ver = key.split("@v")
    design = e2.get_architecture(arch_id, int(ver))
    intent = parse_intent(instruction, design)
    progress(f"Intent: constraints={intent.constraints} objectives={intent.objectives} strategy={intent.preferred_strategy}")
    constraints = list(dict.fromkeys(parent.constraints + intent.constraints))
    changes, critique = [], []
    if intent.needs_architecture_revision and intent.revision_request:
        fb = ArchitectureFeedback(feedback_id="FB-" + uuid.uuid4().hex[:6].upper(), component_ids=intent.affected_components,
                                  observations=[f"User instruction: {instruction}"] + [f"Constraint: {c}" for c in intent.constraints],
                                  changed_constraints=intent.constraints, requested_change=intent.revision_request, priority="high")
        progress(f"Engine 2 revising {design.key}: {fb.requested_change}")
        new = e2.revise_architecture(arch_id, fb, from_version=design.version)
        d = e2.diff(design, new)
        changes += [f"Architecture {design.key} -> {new.key}", f"added: {d['added']}", f"removed: {d['removed']}",
                    f"modified: {[m['id'] for m in d['modified']]}", f"coverage gaps {d['gaps_before']} -> {d['gaps_after']}"]
        design = new
    strategies = list(STRATEGIES)
    evals = evaluate_all(design, a, constraints, strategies, progress=progress, explore_missing=True)
    pref = intent.preferred_strategy if intent.preferred_strategy != "none" else "balanced"
    evals.sort(key=lambda e: 0 if e.strategy == pref else 1)
    # deterministic comparison vs parent's equivalent strategy
    prev = {e.strategy: e for e in parent.evaluations}
    for e in evals:
        p = prev.get(e.strategy)
        if p and p.total_hours.known and e.total_hours.known:
            dh = e.total_hours.base - p.total_hours.base
            critique.append(f"{e.label}: hours {p.total_hours.base:,.0f} -> {e.total_hours.base:,.0f} ({dh:+,.0f}); "
                            f"reuse share {p.score_breakdown['reuse_share']:.0%} -> {e.score_breakdown['reuse_share']:.0%}; "
                            f"gate violations {len(p.hard_gate_violations)} -> {len(e.hard_gate_violations)}; "
                            f"unknowns {len(p.unknown_estimates)} -> {len(e.unknown_estimates)}")
    it = Iteration(iteration_id=new_iteration_id(), parent_iteration_id=parent.iteration_id, user_instruction=instruction,
                   constraints=constraints, objectives=intent.objectives, proposals=[design.key], evaluations=evals,
                   critique=critique, changes=changes, explanation=intent.explanation)
    store.save("iteration", it.iteration_id, it)
    _index_add(it)
    return it


def _index_add(it: Iteration):
    idx = store.load_raw("iterations_index.json", [])
    idx.append({"iteration_id": it.iteration_id, "parent": it.parent_iteration_id, "instruction": it.user_instruction,
                "proposals": it.proposals, "timestamp": it.timestamp})
    store.save_raw("iterations_index.json", idx)


def list_iterations() -> list[dict]:
    return store.load_raw("iterations_index.json", [])


def load_iteration(iteration_id: str) -> Optional[Iteration]:
    return store.load("iteration", iteration_id, Iteration)
