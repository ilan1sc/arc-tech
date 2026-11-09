"""Deterministic acceptance tests from PRD 1/2/3 (no LLM, no network)."""
from shared.schemas import (ArchitectureDesign, CandidateRanking, Component, ComponentSearchSpec, CoverageEntry,
                            EffortRange, ExternalSystem, Interface, PassportCapability, Requirement,
                            SoftwareCapabilityPassport, AdaptationEffortHours, PassportSource, PassportValidation,
                            DataStore, Capability)
from engine1_explore.passport import custom_development_candidate, license_class
from engine1_explore.rank import rank_component, verify_arithmetic
from engine2_architect.validate import compute_coverage, validate
from engine2_architect import mermaid
from engine3_optimize.effort import EffortAssumptions
from engine3_optimize.evaluate import Inputs, choose, evaluate, overlay


def design():
    reqs = [Requirement(id="SL-FT-01", text="track", kind="functional", priority="mandatory", status="explicit"),
            Requirement(id="SL-FT-02", text="history", kind="functional", priority="mandatory", status="explicit"),
            Requirement(id="SL-SEC-01", text="All data shall remain on-premises", kind="constraint", priority="mandatory", status="explicit")]
    caps = [Capability(id="CAP.TRACK", name="Tracking", level="domain"),
            Capability(id="CAP.TRACK.LIVE", name="Live GPS tracking", level="capability", parent_id="CAP.TRACK", requirement_ids=["SL-FT-01"]),
            Capability(id="CAP.TRACK.HISTORY", name="Persistent position history", level="capability", parent_id="CAP.TRACK", requirement_ids=["SL-FT-02"])]
    comps = [Component(id="C-TRACK", name="Tracking service", required_capabilities=["CAP.TRACK.LIVE", "CAP.TRACK.HISTORY"],
                       requirement_ids=["SL-FT-01", "SL-FT-02", "SL-SEC-01"]),
             Component(id="C-UI", name="Map UI", kind="ui", requirement_ids=["SL-FT-01"])]
    d = ArchitectureDesign(architecture_id="T", requirements=reqs, capabilities=caps, components=comps,
                           external_systems=[ExternalSystem(id="X-SAM", name="SAM", fictional=True)],
                           data_stores=[DataStore(id="DS-POS", name="positions", owner_component="C-TRACK")],
                           interfaces=[Interface(id="IF-01", source="X-SAM", target="C-TRACK", name="pos", security="mTLS"),
                                       Interface(id="IF-02", source="C-TRACK", target="C-UI", name="tracks", mode="sync")])
    d.coverage = compute_coverage(d)
    d.validation_findings = validate(d)
    return d


def passport(pid="PP-GL-1", lic="MIT", covs=("full", "none")):
    return SoftwareCapabilityPassport(
        passport_id=pid, software_name="gps-tracker", source=PassportSource(repository_url="https://gitlab.com/x/y"),
        capabilities=[PassportCapability(name="live", capability_id="CAP.TRACK.LIVE", coverage=covs[0], evidence_status="declared",
                                         evidence_refs=["README.md@abc"]),
                      PassportCapability(name="history", capability_id="CAP.TRACK.HISTORY", coverage=covs[1])],
        interfaces=["REST"], license=lic, maturity="stable",
        adaptation_effort_hours=AdaptationEffortHours(estimate=80, confidence="low"), evidence=[],
        validation=PassportValidation(status="passed"), revision="abc")


def spec():
    return ComponentSearchSpec(component_id="C-TRACK", name="Tracking service",
                               required_capabilities=["CAP.TRACK.LIVE", "CAP.TRACK.HISTORY"],
                               capability_names={"CAP.TRACK.LIVE": "Live GPS tracking", "CAP.TRACK.HISTORY": "Persistent position history"})


# ---- PRD 2
def test_mandatory_requirements_allocated_or_gap():
    d = design()
    assert {c.requirement_id for c in d.coverage} == {r.id for r in d.requirements}
    assert all(c.status == "covered" for c in d.coverage)


def test_dangling_interface_is_flagged():
    d = design()
    d.interfaces.append(Interface(id="IF-99", source="C-TRACK", target="C-GHOST", name="x"))
    assert any(f.rule == "dangling-endpoint" and f.severity == "critical" for f in validate(d))


def test_mermaid_renders_and_overlay_keeps_ids():
    d = design()
    src = mermaid.render(d)
    assert "C_TRACK" in src and "IF" not in src.split("flowchart LR")[0]


# ---- PRD 1
def test_missing_history_shows_as_gap():
    r = rank_component(spec(), [passport()])[0]
    assert r.eligible and r.missing_capabilities == ["CAP.TRACK.HISTORY"]
    assert verify_arithmetic(r)


def test_gpl_excluded_with_visible_reason():
    r = rank_component(spec(), [passport(lic="gpl-3.0")])[0]
    assert not r.eligible and "SL-DEP-02" in r.exclusion_reasons[0]


def test_unknown_license_marked_unknown_not_excluded():
    assert license_class("unknown") == "unknown"
    r = rank_component(spec(), [passport(lic="unknown")])[0]
    assert r.eligible and any("Legal review" in m for m in r.required_modifications)


def test_custom_development_candidate_always_available():
    c = custom_development_candidate(spec())
    assert c.is_custom_development and all(x.coverage == "full" for x in c.capabilities)


# ---- PRD 3
def _evals(rate):
    d = design()
    p, cust = passport(), custom_development_candidate(spec())
    rk = {"C-TRACK": rank_component(spec(), [p, cust])}
    inp = Inputs(d, rk, {p.passport_id: p, cust.passport_id: cust})
    a = EffortAssumptions(hourly_rate=rate)
    return [evaluate(inp, choose(inp, s, a, []), a, s, s, []) for s in ("max_reuse", "build_heavy")], a


def test_rate_change_recomputes_money_not_hours():
    (e1, _), _ = _evals(100)
    (e2_, _), _ = _evals(200)
    assert e1.total_hours == e2_.total_hours
    assert abs(e2_.labor_cost_range.base - 2 * e1.labor_cost_range.base) < 1e-6


def test_two_alternatives_have_distinct_choices():
    (reuse, build), _ = _evals(100)
    assert {o.decision for o in reuse.component_options} != {o.decision for o in build.component_options} or \
        reuse.total_hours.base != build.total_hours.base


def test_missing_estimates_unknown_not_zero():
    assert not (EffortRange(low=1, base=2, high=3) + EffortRange()).known
    (reuse, _), a = _evals(100)
    ov = overlay(reuse, a)
    assert "C-TRACK" in ov.nodes and set(ov.edges) == {"IF-01", "IF-02"}


def test_offline_constraint_flags_noncompliant():
    (reuse, _), a = _evals(100)
    d = design()
    d.constraints = ["offline-only"]
    for o in reuse.component_options:
        o.offline_capable = False if o.decision == "REUSE" else o.offline_capable
    from engine3_optimize.evaluate import evaluate as ev_
    p, cust = passport(), custom_development_candidate(spec())
    inp = Inputs(d, {}, {p.passport_id: p})
    out = ev_(inp, reuse.component_options, a, "x", "max_reuse", ["offline-only"])
    assert out.hard_gate_violations and not out.feasible
