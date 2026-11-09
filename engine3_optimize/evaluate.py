"""Build/Buy/Reuse assignment, architecture-wide evaluation, overlays and Pareto shortlist."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from shared.schemas import (ArchitectureDesign, ArchitectureEvaluation, CandidateRanking, ComponentOption,
                            EffortEstimate, EffortRange as R, NonLaborCost, Overlay, OverlayValue,
                            SoftwareCapabilityPassport)

from .effort import EffortAssumptions, with_activities

ROOT = Path(__file__).resolve().parents[1]
COTS = json.loads((ROOT / "data" / "commercial_options.json").read_text())["options"]

STRATEGIES = {
    "balanced": "Reuse a candidate only if it covers at least half of the required capabilities, has a compatible license, "
                "and is cheaper in base hours than building; otherwise build. Commercial options only if offline-capable.",
    "max_reuse": "Reuse wherever any eligible candidate exists (even partial coverage, missing parts built as extensions); "
                 "buy commercial placeholders where no open-source candidate exists.",
    "build_heavy": "Build in-house except where a permissive, mature, judge-validated (PASS) candidate covers all required capabilities.",
}


class Inputs:
    """Everything Engine 3 needs, gathered from Engine 2 (design) and Engine 1 (passports + rankings)."""
    def __init__(self, design: ArchitectureDesign, rankings: dict[str, list[CandidateRanking]],
                 passports: dict[str, SoftwareCapabilityPassport]):
        self.design, self.rankings, self.passports = design, rankings, passports


def _build_hours(kind: str, a: EffortAssumptions) -> R:
    return a.build_hours_by_kind.get(kind, a.build_hours_by_kind["service"])


def _cots_for(component, offline_required: bool):
    caps = component.required_capabilities
    for o in COTS:
        share = sum(any(c.startswith(p) for p in o["capability_prefixes"]) for c in caps) / max(1, len(caps))
        if share >= 0.5:   # commercial option must match most of the component's capabilities
            if offline_required and not o["offline_capable"]:
                continue
            return o
    return None


def _offline_required(design: ArchitectureDesign) -> bool:
    text = " ".join(design.constraints + [r.text for r in design.requirements if r.id.startswith(("SL-SEC", "SL-MAP-02"))]).lower()
    return "offline" in text or "on-premises" in text


def option_for(inp: Inputs, comp, decision: str, ranking: Optional[CandidateRanking], a: EffortAssumptions,
               cots: Optional[dict] = None) -> ComponentOption:
    d = inp.design
    build = _build_hours(comp.kind, a)
    assumptions, nonlabor, evidence = [], [], []
    if decision == "BUILD":
        core = build
        assumptions.append(f"BUILD hours from editable '{comp.kind}' baseline {build.low:.0f}/{build.base:.0f}/{build.high:.0f} h")
        cand_id, cand_name, cov, gaps, lic, offline = f"PP-CUSTOM-{comp.id}", "Custom development", comp.required_capabilities, [], "in-house", True
    elif decision == "REUSE":
        p = inp.passports[ranking.candidate_id]
        est = p.adaptation_effort_hours.estimate
        lo, hi = a.reuse_estimate_spread
        adapt = R(low=est * lo, base=est, high=est * hi)
        miss_share = len(ranking.missing_capabilities) / max(1, len(comp.required_capabilities))
        ext = build.scale(miss_share * a.reuse_missing_capability_build_factor)
        core = a.reuse_onboarding_hours + adapt + ext
        assumptions += [f"Adaptation from passport estimate {est:.0f} h ({p.adaptation_effort_hours.confidence} confidence), spread x{lo}-x{hi}",
                        f"Missing capabilities ({miss_share:.0%}) built as extensions at {a.reuse_missing_capability_build_factor:.0%} of BUILD hours",
                        "Onboarding/learning curve included"]
        cand_id, cand_name, cov, gaps, lic = p.passport_id, p.software_name, ranking.covered_capabilities, ranking.missing_capabilities, p.license
        offline = None if not p.deployment_constraints else not any(w in " ".join(p.deployment_constraints).lower() for w in ("internet", "cloud", "online"))
        evidence = [e.source_ref for e in p.evidence][:6]
        nonlabor.append(NonLaborCost(label=f"License: {p.license}", one_time=R(low=0, base=0, high=0) if p.cost_inputs.license_pricing_known else R(),
                                     known=p.cost_inputs.license_pricing_known, note=p.cost_inputs.license_pricing_note))
    else:  # BUY
        f = a.buy_integration_fraction
        core = R(low=build.low * f.low, base=build.base * f.base, high=build.high * f.high)
        price = cots.get("acquisition_cost")
        acq = R(low=price, base=price, high=price) if price is not None else R()
        nonlabor.append(NonLaborCost(label=f"Acquisition: {cots['name']}", one_time=acq, known=price is not None,
                                     recurring_per_year=acq.scale(a.buy_maintenance_fraction_per_year) if price is not None else R(),
                                     note=cots.get("notes", "") + ("" if price is not None else " — PRICE UNKNOWN")))
        assumptions.append(f"BUY: configuration/integration {f.low:.0%}-{f.high:.0%} of BUILD baseline; pricing {'entered' if price else 'unknown'}")
        cand_id, cand_name, cov, gaps, lic, offline = cots["candidate_id"], cots["name"], comp.required_capabilities, [], cots["license"], cots["offline_capable"]
    total, breakdown = with_activities(core, a)
    eff = EffortEstimate(target_id=comp.id, target_kind="component", hours=total, breakdown=breakdown,
                         confidence="low" if decision != "BUILD" else "medium",
                         source="Engine 3 parametric model + Engine 1 passport" if decision == "REUSE" else "Engine 3 parametric model",
                         assumptions=assumptions)
    return ComponentOption(architecture_id=d.architecture_id, component_id=comp.id, candidate_id=cand_id,
                           candidate_name=cand_name, decision=decision, coverage=cov, gaps=gaps,
                           interface_fit=(ranking.dimension_scores.get("interface_fit") if ranking else None),
                           adaptation_effort_range=core, effort=eff, nonlabor_costs=nonlabor, offline_capable=offline,
                           license=lic, evidence_refs=evidence, assumptions=assumptions,
                           rationale=(ranking.explanation if ranking else ""))


def choose(inp: Inputs, strategy: str, a: EffortAssumptions, constraints: list[str]) -> list[ComponentOption]:
    offline = _offline_required(inp.design) or any("offline" in c.lower() for c in constraints)
    out = []
    for comp in inp.design.components:
        ranks = [r for r in inp.rankings.get(comp.id, []) if r.eligible and not r.candidate_id.startswith("PP-CUSTOM")]
        if offline:   # hard gate: drop candidates that are known to need online services
            ranks = [r for r in ranks if r.dimension_scores.get("operational_fit") not in (0.3,)]
        best = ranks[0] if ranks else None
        build_opt = option_for(inp, comp, "BUILD", None, a)
        reuse_opt = option_for(inp, comp, "REUSE", best, a) if best else None
        cots = _cots_for(comp, offline)
        if strategy == "max_reuse":
            pick = reuse_opt or (option_for(inp, comp, "BUY", None, a, cots) if cots else build_opt)
        elif strategy == "build_heavy":
            bp = inp.passports[best.candidate_id] if best else None
            ok = best and not best.missing_capabilities and best.dimension_scores.get("maturity") == 1.0 \
                and bp.cost_inputs.license_pricing_known and bp.validation.status == "passed"
            pick = reuse_opt if ok else build_opt
        else:  # balanced
            ok = best and len(best.covered_capabilities) >= len(comp.required_capabilities) / 2 \
                and reuse_opt.effort.hours.base < build_opt.effort.hours.base
            pick = reuse_opt if ok else build_opt
        out.append(pick)
    return out


def evaluate(inp: Inputs, options: list[ComponentOption], a: EffortAssumptions, label: str, strategy: str,
             constraints: list[str]) -> ArchitectureEvaluation:
    d = inp.design
    dec = {o.component_id: o.decision for o in options}
    names = {c.id: c for c in d.components}
    ext = {e.id: e for e in d.external_systems}
    itf_eff = []
    for i in d.interfaces:
        base = a.interface_hours_by_mode.get(i.mode, a.interface_hours_by_mode["async"])
        f, why = 1.0, []
        if any(dec.get(x) in ("REUSE", "BUY") for x in (i.source, i.target)):
            f *= a.third_party_interface_factor
            why.append(f"x{a.third_party_interface_factor} data-model conversion (third-party endpoint)")
        if any(ext.get(x) and ext[x].fictional for x in (i.source, i.target)):
            f *= a.fictional_device_interface_factor
            why.append(f"x{a.fictional_device_interface_factor} fictional device interface (no spec yet)")
        hours, br = with_activities(base.scale(f), a)
        itf_eff.append(EffortEstimate(target_id=i.id, target_kind="interface", hours=hours, breakdown=br,
                                      source="Engine 3 parametric model", confidence="low",
                                      assumptions=[f"{i.mode} interface baseline {base.base:.0f} h"] + why))
    shared = [EffortEstimate(target_id=f"SHARED-{k[:12]}", target_kind="shared", hours=v, source="Engine 3 shared work (counted once)",
                             assumptions=[k]) for k, v in a.shared_work.items()]
    comp_total = sum((o.effort.hours for o in options), R(low=0, base=0, high=0))
    itf_total = sum((e.hours for e in itf_eff), R(low=0, base=0, high=0))
    shared_total = sum((e.hours for e in shared), R(low=0, base=0, high=0))
    subtotal = comp_total + itf_total + shared_total
    total = subtotal + subtotal.scale(a.risk_reserve_fraction)
    verification = sum((o.effort.breakdown.get("testing", R()) + o.effort.breakdown.get("security", R()) for o in options), R(low=0, base=0, high=0))
    acq = R(low=0, base=0, high=0)
    unknown = []
    for o in options:
        for c in o.nonlabor_costs:
            if c.one_time.known:
                acq = acq + c.one_time
            else:
                unknown.append(f"{o.component_id}: {c.label} ({c.note})")
    if unknown:
        acq_disp = R()   # at least one unknown price -> total acquisition unknown
    else:
        acq_disp = acq
    labor = a.labor(total)
    lifecycle = labor + acq_disp if acq_disp.known else R()
    # hard gates
    violations = []
    offline = _offline_required(d) or any("offline" in c.lower() for c in constraints)
    for o in options:
        if offline and o.offline_capable is False:
            violations.append(f"{o.component_id}: {o.candidate_name} is not offline-capable")
        if o.decision == "REUSE" and o.license.lower().startswith(("gpl", "agpl")):
            violations.append(f"{o.component_id}: license {o.license} conflicts with SL-DEP-02")
        if offline and o.decision == "REUSE" and o.offline_capable is None:
            unknown.append(f"{o.component_id}: offline capability of {o.candidate_name} not evidenced")
    mand = [r for r in d.requirements if r.priority == "mandatory"]
    gaps = {c.requirement_id for c in d.coverage if c.status == "gap"}
    mcov = (len([r for r in mand if r.id not in gaps]) / len(mand)) if mand else None
    unresolved = [f"{r} not allocated (Engine 2 gap)" for r in sorted(gaps)] + \
                 [f"{o.component_id}: build extension for {', '.join(o.gaps)}" for o in options if o.gaps]
    risks = sorted({r for o in options if o.decision == "REUSE" for r in (inp.passports[o.candidate_id].risks[:2])})
    reuse_share = sum(1 for o in options if o.decision != "BUILD") / max(1, len(options))
    return ArchitectureEvaluation(
        architecture_id=d.architecture_id, architecture_version=d.version, label=label, strategy=strategy,
        component_options=options, interface_efforts=itf_eff + shared, mandatory_coverage=mcov,
        integration_effort_range=itf_total, development_effort_range=comp_total, verification_effort_range=verification,
        total_hours=total, hourly_rate=a.hourly_rate, labor_cost_range=labor, acquisition_cost_range=acq_disp,
        lifecycle_cost_range=lifecycle, unknown_estimates=unknown, risks=risks, unresolved_gaps=unresolved,
        hard_gate_violations=violations, feasible=not violations and (mcov or 0) >= 1.0 - 1e-9,
        score_breakdown={"total_hours_base": total.base, "reuse_share": round(reuse_share, 2),
                         "mandatory_coverage": mcov, "risk_count": float(len(risks) + len(unknown)),
                         "shared_hours_base": shared_total.base, "risk_reserve_fraction": a.risk_reserve_fraction})


def pareto(evals: list[ArchitectureEvaluation]) -> list[ArchitectureEvaluation]:
    """Keep non-dominated feasible options on (hours down, risk down, reuse up). No single fabricated winner."""
    def vec(e):
        s = e.score_breakdown
        return (s["total_hours_base"] or 1e12, s["risk_count"], -s["reuse_share"])
    feas = [e for e in evals if e.feasible]
    for e in evals:
        e.pareto = e in feas and not any(all(x <= y for x, y in zip(vec(o), vec(e))) and vec(o) != vec(e) for o in feas)
    return [e for e in evals if e.pareto]


def overlay(ev: ArchitectureEvaluation, a: EffortAssumptions) -> Overlay:
    nodes = {o.component_id: OverlayValue(hours=o.effort.hours, decision=o.decision, label=o.candidate_name,
                                          money=(a.labor(o.effort.hours) + o.nonlabor_costs[0].one_time) if o.nonlabor_costs and o.nonlabor_costs[0].known
                                          else (a.labor(o.effort.hours) if not o.nonlabor_costs else R()))
             for o in ev.component_options}
    edges = {e.target_id: OverlayValue(hours=e.hours, money=a.labor(e.hours)) for e in ev.interface_efforts if e.target_kind == "interface"}
    money_total = ev.labor_cost_range + ev.acquisition_cost_range if ev.acquisition_cost_range.known else R()
    return Overlay(architecture_id=ev.architecture_id, architecture_version=ev.architecture_version, nodes=nodes, edges=edges,
                   total_hours=ev.total_hours, total_money=money_total, hourly_rate=a.hourly_rate)
