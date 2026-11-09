import json

import ui
import pandas as pd
import streamlit as st

from engine2_architect import api as e2, mermaid
from engine3_optimize import orchestrator as e3
from engine3_optimize.evaluate import overlay as make_overlay

ui.page("2 · Architecture (Engine 2)", "🏗️")
a = ui.assumptions_editor()
d0 = e2.get_architecture("ARCH-SWISSLINK")
if d0 is None:
    st.warning("Generate the architecture on page 1 first.")
    st.stop()
vers = e2.list_versions(d0.architecture_id)
c1, c2, c3 = st.columns([1, 2, 2])
v = c1.selectbox("Version", vers, index=len(vers) - 1)
d = e2.get_architecture(d0.architecture_id, v)
mode = c2.radio("Overlay (from Engine 3)", ["none", "hours", "money"], horizontal=True,
                help="Same graph and ids; Engine 3 overlays effort hours or money without changing the architecture.")

ov, ev = None, None
if mode != "none":
    its = [e3.load_iteration(i["iteration_id"]) for i in e3.list_iterations()]
    evs = [e for it in its if it for e in it.evaluations if e.architecture_version == d.version]
    if evs:
        labels = list(dict.fromkeys(e.label for e in evs))
        pick = c3.selectbox("Evaluation", labels)
        ev = [e for e in evs if e.label == pick][-1]
        ov = make_overlay(ev, a)
    else:
        c3.info("No Engine 3 evaluation for this version yet — run the Optimizer (page 4).")

comp_ids = [c.id for c in d.components]
sel = st.selectbox("Component details", ["—"] + comp_ids,
                   format_func=lambda x: x if x == "—" else f"{x} · {next(c.name for c in d.components if c.id == x)}")
src = mermaid.render(d, ov, mode, a.currency, highlight={sel} if sel != "—" else None)

if ov is not None:
    m1, m2, m3 = st.columns(3)
    m1.metric("Total engineering hours (base)", f"{ov.total_hours.base:,.0f} h" if ov.total_hours.known else "unknown",
              help=ui.fmt(ov.total_hours))
    m2.metric(f"Total money ({a.currency})", f"{ov.total_money.base:,.0f}" if ov.total_money.known else "unknown",
              help="Unknown if any purchase/license price is missing")
    m3.metric("Labor only", f"{ev.labor_cost_range.base:,.0f} {a.currency}" if ev.labor_cost_range.known else "unknown",
              help=f"hours × {a.hourly_rate} {a.currency}/h")
    if ev.unknown_estimates:
        st.caption("Unknown: " + "; ".join(ev.unknown_estimates[:6]))

left, right = st.columns([3, 1.3])
with left:
    ui.mermaid(src, height=780, key="arch")
with right:
    if sel != "—":
        c = next(c for c in d.components if c.id == sel)
        st.subheader(f"{c.name}")
        st.caption(f"`{c.id}` · {c.kind} · {c.subsystem} · trust zone: {c.trust_zone}")
        st.write(c.purpose)
        st.markdown("**Required capabilities:** " + ", ".join(f"`{x}`" for x in c.required_capabilities))
        st.markdown("**Requirements:** " + ", ".join(c.requirement_ids))
        for label, items in [("Responsibilities", c.responsibilities), ("Inputs", c.inputs), ("Outputs", c.outputs),
                             ("Data owned", c.data_owned), ("Depends on", c.dependencies),
                             ("Runtime / deployment", c.runtime_assumptions + c.deployment_assumptions),
                             ("Quality constraints", c.quality_constraints), ("Design assumptions", c.design_assumptions)]:
            if items:
                st.markdown(f"**{label}**\n" + "\n".join(f"- {i}" for i in items))
        itf = [i for i in d.interfaces if sel in (i.source, i.target)]
        if itf:
            st.markdown("**Interfaces**")
            for i in itf:
                st.markdown(f"- `{i.id}` {i.source} → {i.target}: {i.name} ({i.mode}; {', '.join(i.protocol_candidates)})")
        if ov and sel in ov.nodes:
            n = ov.nodes[sel]
            st.markdown(f"**Engine 3:** {ui.badge(n.decision or '', ui.DECISION_COLOR.get(n.decision, '#eee'))} {n.label}",
                        unsafe_allow_html=True)
            st.markdown(f"Hours: {ui.fmt(n.hours)}  \nMoney: {ui.fmt(n.money, money=True, currency=a.currency)}")
    else:
        st.subheader("Design rationale")
        st.write(d.design_rationale)

t1, t2, t3, t4, t5 = st.tabs(["Validation findings", "Interfaces", "Assumptions & risks", "Change log / diff", "JSON"])
with t1:
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    df = pd.DataFrame([f.model_dump() for f in sorted(d.validation_findings, key=lambda f: sev_order[f.severity])])
    st.dataframe(df, width="stretch", hide_index=True)
    gaps = [c for c in d.coverage if c.status == "gap"]
    st.caption(f"Coverage: {len(d.coverage) - len(gaps)}/{len(d.coverage)} requirements allocated; gaps: {[g.requirement_id for g in gaps]}")
with t2:
    st.dataframe(pd.DataFrame([{"id": i.id, "from": i.source, "to": i.target, "name": i.name, "mode": i.mode,
                                "protocols": ", ".join(i.protocol_candidates), "payload": i.payload, "security": i.security,
                                "errors": i.error_handling} for i in d.interfaces]), width="stretch", hide_index=True)
with t3:
    st.markdown("**Assumptions**\n" + "\n".join(f"- {x}" for x in d.assumptions))
    st.markdown("**Risks**\n" + "\n".join(f"- {x}" for x in d.risks))
    st.markdown("**Constraints applied**\n" + ("\n".join(f"- {x}" for x in d.constraints) or "_none beyond SRS_"))
with t4:
    for ch in d.change_log:
        st.markdown(f"**v{ch.version}** — {ch.summary}  \n<small>{ch.reason}</small>", unsafe_allow_html=True)
        if ch.added or ch.removed or ch.modified:
            st.markdown(f"➕ {ch.added}  \n➖ {ch.removed}  \n✏️ {ch.modified}")
    if d.parent_id:
        pid, pv = d.parent_id.split("@v")
        st.json(e2.diff(e2.get_architecture(pid, int(pv)), d))
with t5:
    st.download_button("Download architecture JSON", d.model_dump_json(indent=2), f"{d.architecture_id}_v{d.version}.json")
    st.download_button("Download Mermaid", src, f"{d.architecture_id}_v{d.version}.mmd")
    st.download_button("Download ComponentSearchSpec[] (for Engine 1)",
                       json.dumps([s.model_dump() for s in e2.get_component_requirements(d.architecture_id, d.version)], indent=2),
                       "component_search_specs.json")
    with st.expander("Raw JSON"):
        st.json(json.loads(d.model_dump_json()))
