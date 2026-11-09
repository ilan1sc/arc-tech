import ui
import pandas as pd
import streamlit as st

from engine2_architect import api as e2, mermaid
from engine3_optimize import orchestrator as e3
from engine3_optimize.evaluate import choices_for, overlay as make_overlay, pareto, rebuild
from shared import store

ui.page("4 · Build/Buy/Reuse optimizer & chat (Engine 3)", "⚙️")
ui.model_selector("engine3", "engine2", "engine1")
a = ui.assumptions_editor()
aid = ui.current_arch_id()

idx = [i for i in e3.list_iterations() if any(k.startswith(f"{aid}@") for k in i["proposals"])]
c1, c2 = st.columns([3, 1])
explore = c2.checkbox("Let Engine 1 explore missing components (slow, live)", value=False)
if c2.button("Start new evaluation", type="primary" if not idx else "secondary"):
    with st.status("Engine 3 orchestrating Engine 2 + Engine 1…", expanded=True) as s:
        it = e3.start(ui.SRS_PATH.read_text(), a, progress=lambda m: s.write(m), explore=explore, architecture_id=aid)
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

with st.form("refine", clear_on_submit=True, border=True):
    fc1, fc2 = st.columns([5, 1])
    msg = fc1.text_input("💬 Refine this iteration", placeholder='e.g. "Too expensive; maximize reuse" · "Offline only" · "Reduce cost"')
    go = fc2.form_submit_button("Refine", type="primary", width="stretch")
if go and msg.strip():
    with st.status(f"Refining: {msg}", expanded=True) as s:
        new = e3.refine(it, msg.strip(), a, progress=lambda m: s.write(m), explore=explore)
        s.update(label=f"New iteration {new.iteration_id}", state="complete")
    st.session_state.it = new.iteration_id
    st.rerun()

parent = e3.load_iteration(it.parent_iteration_id) if it.parent_iteration_id else None
if parent and parent.evaluations and it.evaluations:
    pl, nl = parent.evaluations[0], it.evaluations[0]
    def money(ev):
        lab = a.labor(ev.total_hours)
        return (lab + ev.acquisition_cost_range) if ev.acquisition_cost_range.known else None, lab
    (pm, plab), (nm, nlab) = money(pl), money(nl)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lead option", nl.label.split(" (")[0], f"was {pl.label.split(' (')[0]}", delta_color="off")
    c2.metric("Total hours (base)", f"{nl.total_hours.base:,.0f}", f"{nl.total_hours.base - pl.total_hours.base:+,.0f} h", delta_color="inverse")
    c3.metric(f"Labor @ {a.hourly_rate:,.0f} {a.currency}/h", f"{nlab.base:,.0f}", f"{nlab.base - plab.base:+,.0f}", delta_color="inverse")
    c4.metric(f"Total money ({a.currency})", f"{nm.base:,.0f}" if nm else "unknown",
              (f"{nm.base - pm.base:+,.0f}" if nm and pm else "price(s) unknown"), delta_color="inverse")
if it.user_instruction:
    st.markdown(f"**Instruction:** _{it.user_instruction}_")
if it.constraints or it.objectives:
    st.markdown("**Constraints (hard gates):** " + (", ".join(it.constraints) or "none") +
                "  \n**Objectives:** " + (", ".join(it.objectives) or "none"))
if it.changes:
    st.markdown("**Changes:**\n" + "\n".join(f"- {c}" for c in it.changes))
if it.critique:
    import re
    crit = [re.sub(r"; labor [^;]*USD", "", c) for c in it.critique]   # money shown live above, at the current rate
    st.markdown("**What improved / worsened vs parent:**\n" + "\n".join(f"- {c}" for c in crit))

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

arch_id, ver = ev.architecture_id, ev.architecture_version
d = e2.get_architecture(arch_id, ver)
inp = e3.gather(d)
okey = f"{it.iteration_id}|{ev.label}"
overrides = st.session_state.setdefault("overrides", {}).setdefault(okey, {})
baseline = rebuild(inp, ev, {}, a, it.constraints, ev.label)                 # same option, current assumptions
cur = rebuild(inp, ev, overrides, a, it.constraints, f"{ev.label.split(' (')[0]} · edited") if overrides else baseline

st.subheader("Per-component Build / Buy / Reuse")
st.caption("👆 Click a component to change its decision — hours and money update immediately.")
rows = []
for o in cur.component_options:
    rows.append({"component": o.component_id, "name": next((c.name for c in d.components if c.id == o.component_id), ""),
                 "decision": ("✏️ " if o.component_id in overrides else "") + o.decision, "candidate": o.candidate_name,
                 "license": o.license, "hours": ui.fmt(o.effort.hours),
                 f"labor {a.currency}": ui.fmt(a.labor(o.effort.hours), money=True),
                 "non-labor": "; ".join(f"{c.label}: {'known' if c.known else 'UNKNOWN'}" for c in o.nonlabor_costs),
                 "gaps (built as extension)": ", ".join(o.gaps), "offline": o.offline_capable,
                 "assumptions": " | ".join(o.assumptions)})
sel = st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row",
                   key=f"comp_tbl_{okey}", column_config={"decision": st.column_config.TextColumn(width="small")})
picked = sel.selection.rows if sel and sel.selection else []
if picked:
    o = cur.component_options[picked[0]]
    comp = next(c for c in d.components if c.id == o.component_id)
    ch = choices_for(inp, comp, it.constraints)
    keys = [(dec, cid) for dec, cid, _ in ch]
    current = (o.decision, o.candidate_id if o.decision != "BUILD" else None)
    idx = keys.index(current) if current in keys else 0
    with st.container(border=True):
        st.markdown(f"**✏️ {comp.id} · {comp.name}** — {comp.purpose}")
        choice = st.radio("Decision", range(len(ch)), index=idx, format_func=lambda i: ch[i][2], key=f"choice_{okey}_{comp.id}")
        new = keys[choice]
        orig = next(x for x in ev.component_options if x.component_id == comp.id)
        if new != current:
            if new == (orig.decision, orig.candidate_id if orig.decision != "BUILD" else None):
                overrides.pop(comp.id, None)
            else:
                overrides[comp.id] = new
            st.rerun()

if overrides:
    dh = cur.total_hours.base - baseline.total_hours.base
    dl = a.labor(cur.total_hours).base - a.labor(baseline.total_hours).base
    with st.container(border=True):
        st.markdown(f"**What-if: {len(overrides)} manual change(s) to {ev.label.split(' (')[0]}** — "
                    + ", ".join(f"`{k}` → {v[0]}" for k, v in overrides.items()))
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total hours (base)", f"{cur.total_hours.base:,.0f}", f"{dh:+,.0f} h", delta_color="inverse")
        k2.metric(f"Labor @ {a.hourly_rate:,.0f} {a.currency}/h", f"{a.labor(cur.total_hours).base:,.0f}", f"{dl:+,.0f}", delta_color="inverse")
        tm = (a.labor(cur.total_hours) + cur.acquisition_cost_range) if cur.acquisition_cost_range.known else None
        k3.metric(f"Total money ({a.currency})", f"{tm.base:,.0f}" if tm else "unknown",
                  "price(s) unknown" if not tm else None, delta_color="off")
        k4.metric("Reuse share", f"{cur.score_breakdown['reuse_share']:.0%}",
                  f"{(cur.score_breakdown['reuse_share'] - baseline.score_breakdown['reuse_share']) * 100:+.0f} pp", delta_color="off")
        if cur.hard_gate_violations:
            st.error("Hard-gate violations: " + "; ".join(cur.hard_gate_violations))
        if len(cur.unknown_estimates) > len(baseline.unknown_estimates):
            st.warning("New unknowns: " + "; ".join(set(cur.unknown_estimates) - set(baseline.unknown_estimates)))
        b1, b2, _ = st.columns([1, 1.4, 3])
        if b1.button("↺ Reset edits"):
            st.session_state.overrides[okey] = {}
            st.rerun()
        if b2.button("💾 Save as a new option", type="primary"):
            n = sum(1 for e in it.evaluations if "edited" in e.strategy) + 1
            cur.label = f"D{n} · Architect edit of {ev.label.split(' (')[0]} ({d.key})"
            it.evaluations.append(cur)
            pareto(it.evaluations)
            it.changes.append(f"Architect saved {cur.label}: " + ", ".join(f"{k} → {v[0]}" for k, v in overrides.items()))
            store.save("iteration", it.iteration_id, it)
            st.session_state.overrides[okey] = {}
            st.success(f"Saved {cur.label} — it now appears in the comparison table.")
            st.rerun()

with st.expander("Interface & shared-work effort (counted once)"):
    st.dataframe(pd.DataFrame([{"target": e.target_id, "kind": e.target_kind, "hours": ui.fmt(e.hours),
                                "assumptions": " | ".join(e.assumptions)} for e in cur.interface_efforts]),
                 width="stretch", hide_index=True)

mode = st.radio("Diagram overlay", ["hours", "money", "none"], horizontal=True)
ui.mermaid(mermaid.render(d, make_overlay(cur, a), mode, a.currency,
                          highlight={o.component_id for o in cur.component_options} if False else set(overrides)),
           height=600, key="opt")

