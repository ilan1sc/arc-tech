import ui
import pandas as pd
import streamlit as st

from engine2_architect import api as e2, mermaid
from engine3_optimize import orchestrator as e3
from engine3_optimize.evaluate import overlay as make_overlay

ui.page("4 · Build/Buy/Reuse optimizer & chat (Engine 3)", "⚙️")
a = ui.assumptions_editor()

idx = e3.list_iterations()
c1, c2 = st.columns([3, 1])
explore = c2.checkbox("Let Engine 1 explore missing components (slow, live)", value=False)
if c2.button("Start new evaluation", type="primary" if not idx else "secondary"):
    with st.status("Engine 3 orchestrating Engine 2 + Engine 1…", expanded=True) as s:
        it = e3.start(ui.SRS_PATH.read_text(), a, progress=lambda m: s.write(m), explore=explore)
        s.update(label=f"Iteration {it.iteration_id} ready", state="complete")
    st.session_state.it = it.iteration_id
    st.rerun()
if not idx:
    st.info("No iterations yet. Start a new evaluation.")
    st.stop()

opts = {i["iteration_id"]: i for i in idx}
default = st.session_state.get("it", idx[-1]["iteration_id"])
cur_id = c1.selectbox("Iteration (all versions kept)", list(opts), index=list(opts).index(default) if default in opts else len(opts) - 1,
                      format_func=lambda k: f"{k} ← {opts[k]['parent'] or 'root'} · {opts[k]['instruction'][:60]} · {', '.join(opts[k]['proposals'])}")
it = e3.load_iteration(cur_id)

# Recompute money with the CURRENT hourly rate (hours unchanged)
for ev in it.evaluations:
    ev.hourly_rate = a.hourly_rate
    ev.labor_cost_range = a.labor(ev.total_hours)
    ev.lifecycle_cost_range = ev.labor_cost_range + ev.acquisition_cost_range if ev.acquisition_cost_range.known else ev.lifecycle_cost_range.__class__()

if it.user_instruction:
    st.markdown(f"**Instruction:** _{it.user_instruction}_")
if it.constraints or it.objectives:
    st.markdown("**Constraints (hard gates):** " + (", ".join(it.constraints) or "none") +
                "  \n**Objectives:** " + (", ".join(it.objectives) or "none"))
if it.changes:
    st.markdown("**Changes:**\n" + "\n".join(f"- {c}" for c in it.changes))
if it.critique:
    st.markdown("**What improved / worsened vs parent:**\n" + "\n".join(f"- {c}" for c in it.critique))

st.subheader("Architecture comparison")
rows = []
for ev in it.evaluations:
    rows.append({"option": ev.label, "pareto": "★" if ev.pareto else "", "feasible": "✅" if ev.feasible else "⛔",
                 "mandatory coverage": f"{ev.mandatory_coverage:.0%}" if ev.mandatory_coverage is not None else "unknown",
                 "reuse share": f"{ev.score_breakdown.get('reuse_share', 0):.0%}",
                 "total hours (low–high)": ui.fmt(ev.total_hours),
                 "components h": ui.fmt(ev.development_effort_range), "integration h": ui.fmt(ev.integration_effort_range),
                 f"labor {a.currency}": ui.fmt(ev.labor_cost_range, money=True),
                 f"acquisition {a.currency}": ui.fmt(ev.acquisition_cost_range, money=True),
                 "unknowns": len(ev.unknown_estimates), "gate violations": len(ev.hard_gate_violations)})
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
st.caption(f"Money = hours × {a.hourly_rate:,.0f} {a.currency}/h (editable) + non-labor. No calendar/staffing estimates "
           "(deferred). ★ = Pareto-efficient (hours, risk, reuse) — no single 'winner' is claimed; the human architect approves.")

labels = [ev.label for ev in it.evaluations]
pick = st.selectbox("Inspect option", labels)
ev = next(e for e in it.evaluations if e.label == pick)
if ev.hard_gate_violations:
    st.error("Hard-gate violations: " + "; ".join(ev.hard_gate_violations))
if ev.unknown_estimates:
    st.warning("Unknown (not zero): " + "; ".join(ev.unknown_estimates))

st.subheader("Per-component Build / Buy / Reuse")
st.dataframe(pd.DataFrame([{
    "component": o.component_id, "decision": o.decision, "candidate": o.candidate_name, "license": o.license,
    "hours": ui.fmt(o.effort.hours), f"labor {a.currency}": ui.fmt(a.labor(o.effort.hours), money=True),
    "non-labor": "; ".join(f"{c.label}: {'known' if c.known else 'UNKNOWN'}" for c in o.nonlabor_costs),
    "covered": len(o.coverage), "gaps (built as extension)": ", ".join(o.gaps), "offline": o.offline_capable,
    "assumptions": " | ".join(o.assumptions), "evidence": ", ".join(o.evidence_refs[:3])} for o in ev.component_options]),
    width="stretch", hide_index=True,
    column_config={"decision": st.column_config.TextColumn(width="small")})

with st.expander("Interface & shared-work effort (counted once)"):
    st.dataframe(pd.DataFrame([{"target": e.target_id, "kind": e.target_kind, "hours": ui.fmt(e.hours),
                                "assumptions": " | ".join(e.assumptions)} for e in ev.interface_efforts]),
                 width="stretch", hide_index=True)

arch_id, ver = ev.architecture_id, ev.architecture_version
d = e2.get_architecture(arch_id, ver)
mode = st.radio("Diagram overlay", ["hours", "money", "none"], horizontal=True)
ui.mermaid(mermaid.render(d, make_overlay(ev, a), mode, a.currency), height=700, key="opt")

st.subheader("💬 Refine")
st.caption('Try: "Too expensive; maximize reuse" · "Offline only" · "Reduce cost"')
msg = st.chat_input("Instruction for the optimizer…")
if msg:
    with st.status(f"Refining: {msg}", expanded=True) as s:
        new = e3.refine(it, msg, a, progress=lambda m: s.write(m), explore=explore)
        s.update(label=f"New iteration {new.iteration_id}", state="complete")
    st.session_state.it = new.iteration_id
    st.rerun()
