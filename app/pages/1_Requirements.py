import ui
import pandas as pd
import streamlit as st

from engine2_architect import api as e2

ui.page("1 · Requirements & capabilities (Engine 2)", "📋")
srs_default = ui.SRS_PATH.read_text()
d = e2.get_architecture("ARCH-SWISSLINK")

with st.expander("SwissLink SRS (fictional)", expanded=d is None):
    srs = st.text_area("SRS text", srs_default, height=300)
    cons = st.text_input("Extra constraints (comma separated)", "")
    if st.button("Generate architecture (Engine 2)", type="primary"):
        with st.status("Engine 2 working… (extraction → capability tree → synthesis → validation)", expanded=True):
            d = e2.generate_architecture(srs, [c.strip() for c in cons.split(",") if c.strip()])
        st.success(f"Generated {d.key}")
        st.rerun()

if d is None:
    st.warning("No architecture yet — generate one above.")
    st.stop()

vers = e2.list_versions(d.architecture_id)
v = st.selectbox("Version", vers, index=len(vers) - 1)
d = e2.get_architecture(d.architecture_id, v)

t1, t2, t3, t4 = st.tabs([f"Requirements ({len(d.requirements)})", f"Open questions ({len(d.open_questions)})",
                          f"Capability tree ({len(d.capabilities)})", "Traceability matrix"])
with t1:
    df = pd.DataFrame([{"id": r.id, "priority": r.priority, "kind": r.kind, "status": r.status, "text": r.text,
                        "ambiguity": r.ambiguity or ""} for r in d.requirements])
    st.dataframe(df, width="stretch", hide_index=True, height=520)
with t2:
    for q in d.open_questions:
        st.markdown(f"- **{q.id}** `{q.kind}` {q.question}  _({', '.join(q.requirement_ids)})_")
with t3:
    kids = {}
    for c in d.capabilities:
        kids.setdefault(c.parent_id, []).append(c)

    def show(parent, depth=0):
        for c in kids.get(parent, []):
            st.markdown(("&nbsp;" * 6 * depth) + f"{'📁' if c.level == 'domain' else '🔹' if c.level == 'capability' else '▫️'} "
                        f"**{c.name}** `{c.id}` <small>{', '.join(c.requirement_ids)}</small>", unsafe_allow_html=True)
            show(c.id, depth + 1)
    show(None)
with t4:
    comps = [c.id for c in d.components]
    rows = []
    for r in d.requirements:
        cov = next((x for x in d.coverage if x.requirement_id == r.id), None)
        row = {"req": r.id, "priority": r.priority, "status": cov.status if cov else "?"}
        for c in comps:
            row[c] = "●" if cov and c in cov.component_ids else ""
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=560)
