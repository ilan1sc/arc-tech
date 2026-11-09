import time

import ui
import pandas as pd
import streamlit as st

from engine2_architect import api as e2

ui.page("1 · Requirements → architecture (Engine 2)", "📋")
ui.model_selector("engine2", "judge")

# ------------------------------------------------------------------ 1. load an SRS and create the architecture
st.subheader("① Load a Software Requirements Specification (SRS)")
src = st.radio("Source", ["SwissLink sample (fictional)", "Upload an SRS file"], horizontal=True, label_visibility="collapsed")
if src.startswith("Upload"):
    f = st.file_uploader("SRS file", type=["md", "txt", "pdf", "docx"],
                         help="Markdown, text, PDF or Word. Requirement IDs are reused if present, otherwise REQ-001… are assigned.")
    srs_text, srs_name = (ui.read_srs_upload(f), f.name) if f else ("", "")
else:
    srs_text, srs_name = ui.SRS_PATH.read_text(), "swisslink_srs.md"

if srs_text:
    with st.expander(f"📄 {srs_name} — {len(srs_text.split()):,} words (click to read / edit)"):
        srs_text = st.text_area("SRS text", srs_text, height=320, label_visibility="collapsed")
    cons = st.text_input("Extra constraints (optional, comma separated)", placeholder="e.g. offline-only, Linux containers")
    if st.button("🏗️ Create architecture", type="primary"):
        t0 = time.time()
        with st.status("Engine 2 is creating the architecture…", expanded=True) as status:
            d = e2.generate_architecture(srs_text, [c.strip() for c in cons.split(",") if c.strip()],
                                         source_name=srs_name, progress=lambda m: (status.write(m), time.sleep(0.6)))
            status.update(label=f"Architecture {d.key} ready in {time.time() - t0:.0f}s", state="complete", expanded=True)
        st.session_state.arch_id = d.architecture_id
        st.page_link("pages/2_Architecture.py", label="Open the architecture →", icon="🏗️")

# ------------------------------------------------------------------ 2. what Engine 2 extracted
aid = ui.current_arch_id()
d = e2.get_architecture(aid) if aid else None
if d is None:
    st.info("No architecture yet — load an SRS and press **Create architecture**.")
    st.stop()

st.divider()
v1 = e2.get_architecture(aid, 1) or d
st.subheader(f"② What Engine 2 understood — {v1.title or d.architecture_id}")
st.caption(f"Source: **{d.source_name or 'SRS'}** · model `{d.generated_with or 'n/a'}` · "
           "requirements are the same in every revision (v1, v2…) of this project; revisions only change the architecture.")
texts = {r.id: r.text for r in d.requirements}
oq_by_req = {}
for q in d.open_questions:
    for rid in q.requirement_ids:
        oq_by_req.setdefault(rid, []).append(q)
unclear = {r.id for r in d.requirements if r.ambiguity or r.id in oq_by_req}
comps_by_req = {c.requirement_id: c.component_ids for c in d.coverage}
names = {c.id: c.name for c in d.components}

m1, m2, m3, m4 = st.columns(4)
m1.metric("Requirements", len(d.requirements), f"{sum(r.priority == 'mandatory' for r in d.requirements)} mandatory", delta_color="off")
m2.metric("Need clarification", len(unclear), help="Requirements that cannot be built or tested as written — each has an open question")
m3.metric("Open questions", len(d.open_questions))
m4.metric("Capabilities", len(d.capabilities))

t1, t2, t3, t4 = st.tabs([f"Requirements ({len(d.requirements)})", f"Open questions ({len(d.open_questions)})",
                          f"Capability tree ({len(d.capabilities)})", "Traceability matrix"])
with t1:
    st.caption("👆 Click a row to read the full requirement, its source, and which components implement it.")
    df = pd.DataFrame([{"ID": r.id, "Priority": r.priority, "Type": r.kind,
                        "Origin": "stated in SRS" if r.status == "explicit" else "inferred by AI",
                        "Requirement": r.text, "Needs clarification": ("⚠️ " + ", ".join(q.id for q in oq_by_req.get(r.id, [])) or "⚠️ yes") if r.id in unclear else ""} for r in d.requirements])
    ev = st.dataframe(df, width="stretch", hide_index=True, height=420, on_select="rerun", selection_mode="single-row",
                      key="req_table",
                      column_config={
                          "Requirement": st.column_config.TextColumn(width="large"),
                          "Needs clarification": st.column_config.TextColumn(
                              help="Engine 2 flags a requirement that can't be built or tested as written — e.g. "
                                   "'low latency' with no number, or a conflict with another requirement. "
                                   "Each flag becomes an open question instead of an invented value."),
                          "Origin": st.column_config.TextColumn(help="'stated in SRS' = numbered statement in the document; "
                                                                     "'inferred by AI' = implied, added by Engine 2 and labelled"),
                      })
    rows = ev.selection.rows if ev and ev.selection else []
    if rows:
        r = d.requirements[rows[0]]
        with st.container(border=True):
            st.markdown(f"### {r.id} · {r.priority} {r.kind} requirement")
            st.markdown(f"> {r.text}")
            if r.source_passage:
                st.caption(f"Source passage: “{r.source_passage}”")
            if r.ambiguity:
                st.warning(f"**Why it needs clarification:** {r.ambiguity}")
            qs = [q for q in d.open_questions if r.id in q.requirement_ids]
            for q in qs:
                st.markdown(f"❓ **{q.id}** ({q.kind.replace('_', ' ')}): {q.question}")
            comps = comps_by_req.get(r.id, [])
            st.markdown("**Implemented by:** " + (", ".join(f"`{c}` {names.get(c, '')}" for c in comps) or "⚠️ not allocated (gap)"))
            caps = [c for c in d.capabilities if r.id in c.requirement_ids]
            if caps:
                st.markdown("**Capabilities:** " + ", ".join(f"{c.name} `{c.id}`" for c in caps))
with t2:
    st.caption("Questions Engine 2 raises instead of inventing numbers or resolving conflicts on its own. Hover an ID to see the requirement.")
    for q in d.open_questions:
        st.markdown(f"- **{q.id}** `{q.kind.replace('_', ' ')}` {q.question} — {ui.req_tips(q.requirement_ids, texts)}",
                    unsafe_allow_html=True)
with t3:
    st.caption("📁 domain → 🔹 capability → ▫️ operation. Hover a requirement ID to see its text.")
    kids = {}
    for c in d.capabilities:
        kids.setdefault(c.parent_id, []).append(c)

    def show(parent, depth=0):
        for c in kids.get(parent, []):
            st.markdown(("&nbsp;" * 6 * depth) + f"{'📁' if c.level == 'domain' else '🔹' if c.level == 'capability' else '▫️'} "
                        f"**{c.name}** <code>{c.id}</code> {ui.req_tips(c.requirement_ids, texts)}", unsafe_allow_html=True)
            show(c.id, depth + 1)
    show(None)
with t4:
    st.caption("● = the component implements the requirement. Hover a column header for the component name.")
    comps = [c.id for c in d.components]
    rows = []
    for r in d.requirements:
        cov = next((x for x in d.coverage if x.requirement_id == r.id), None)
        row = {"ID": r.id, "Requirement": r.text, "Status": "✅ covered" if cov and cov.status == "covered" else "⚠️ gap"}
        for c in comps:
            row[c] = "●" if cov and c in cov.component_ids else ""
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=560,
                 column_config={"Requirement": st.column_config.TextColumn(width="medium"),
                                **{c: st.column_config.TextColumn(width="small", help=names[c]) for c in comps}})
