import ui
import pandas as pd
import streamlit as st

from engine1_explore import api as e1
from engine1_explore.rank import DEFAULT_WEIGHTS, rank_component
from engine2_architect import api as e2

ui.page("3 · Software exploration & passports (Engine 1)", "🔎")
ui.model_selector("engine1", "judge")
aid = ui.current_arch_id()
d = e2.get_architecture(aid) if aid else None
if d is None:
    st.warning("Generate the architecture on page 1 first.")
    st.stop()
specs = {s.component_id: s for s in e2.get_component_requirements(d.architecture_id, d.version)}

with st.sidebar.expander("⚖️ Ranking weights (editable)", expanded=False):
    weights = {k: st.slider(k.replace("_", " "), 0.0, 1.0, float(v), 0.05) for k, v in DEFAULT_WEIGHTS.items()}

mode = st.radio("Mode", ["Architecture component", "Ad-hoc capability search"], horizontal=True)
if mode == "Ad-hoc capability search":
    q = st.text_input("Capability search", "GPS tracking")
    # default: the component that owns the most friendly-force-tracking capabilities
    track_idx = max(range(len(specs)), key=lambda i: sum(c.startswith("CAP.TRACK") for c in list(specs.values())[i].required_capabilities))
    target = st.selectbox("Match against SwissLink component", list(specs), index=track_idx,
                          format_func=lambda k: f"{k} · {specs[k].name}")
    base = specs[target]
    slug = "".join(ch if ch.isalnum() else "-" for ch in q.lower()).strip("-")
    # separate storage slot: ad-hoc searches never overwrite the component's own exploration
    spec = base.model_copy(update={"search_terms": [q], "component_id": f"ADHOC-{target}-{slug}"})
    queries = [q]
    st.caption(f"Results are matched against {target}'s required capabilities and stored separately as `{spec.component_id}`.")
else:
    target = st.selectbox("Component (from Engine 2 ComponentSearchSpec)", list(specs),
                          format_func=lambda k: f"{k} · {specs[k].name}")
    spec = specs[target]
    queries = None
    with st.expander("ComponentSearchSpec sent to Engine 1"):
        st.json(spec.model_dump())

keep = st.slider("Repositories to inspect (bounded analysis)", 1, 5, 2)
res = e1.load_exploration(spec.component_id)
if st.button("Run discovery → inspection → passport → judge → ranking", type="primary"):
    with st.status("Engine 1 working…", expanded=True) as s:
        res = e1.explore_component(spec, queries=queries, keep=keep, progress=lambda m: s.write(m))
        s.update(label="Done", state="complete")

if res is None:
    st.info("No exploration cached for this component yet. Run it above.")
    st.stop()

for e in res.errors:
    st.warning(e)
rankings = rank_component(spec, res.passports, weights)
pp = {p.passport_id: p for p in res.passports}

st.subheader(f"Discovered ({len(res.discovered)} after dedup) — queries: {res.queries}")
st.dataframe(pd.DataFrame([{"inspected": "✅" if h.get("selected") else "", "name": h["name_with_namespace"],
                            "stars": h.get("star_count"), "relevance": h.get("relevance"), "query": h.get("matched_query"),
                            "last activity": (h.get("last_activity_at") or "")[:10], "url": h["web_url"]} for h in res.discovered]),
             width="stretch", hide_index=True, height=220,
             column_config={"url": st.column_config.LinkColumn("url")})

st.subheader("Suitability ranking (component fit only — Engine 3 decides Build/Buy/Reuse)")
rows = []
for r in rankings:
    p = pp[r.candidate_id]
    rows.append({"rank": r.rank or "—", "candidate": p.software_name, "eligible": "✅" if r.eligible else "⛔",
                 "score": r.total_score, "confidence": r.confidence, "license": p.license,
                 **{k: r.dimension_scores.get(k) for k in DEFAULT_WEIGHTS},
                 "covered": len(r.covered_capabilities), "missing": ", ".join(spec.capability_names.get(m, m) for m in r.missing_capabilities),
                 "excluded because": "; ".join(r.exclusion_reasons), "judge": p.validation.status})
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
st.caption("Empty dimension cells = unknown (excluded from the weighted mean and lowers confidence) — not zero.")

st.subheader("Software Capability Passports")
for r in rankings:
    p = pp[r.candidate_id]
    with st.expander(f"{'⭐ ' if r.rank == 1 else ''}{p.software_name} — {p.passport_id}", expanded=r.rank == 1):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"**Source:** {p.source.repository_url or '—'}  \n**Revision:** `{p.revision or 'n/a'}`  \n"
                        f"**License:** {p.license} · **Maturity:** {p.maturity} · **Tests present:** {p.tests_present} · ⭐ {p.stars}")
            st.write(p.description)
            st.markdown("**Capabilities**")
            for c in p.capabilities:
                st.markdown(f"{ui.badge(c.evidence_status, ui.STATUS_COLOR[c.evidence_status])} **{c.name}** "
                            f"`{c.capability_id or '-'}` coverage **{c.coverage}** "
                            f"<small>{'; '.join(c.evidence_refs)}</small><br/><small>{c.notes}</small>", unsafe_allow_html=True)
            if r.missing_capabilities:
                st.error("Missing for this component: " + ", ".join(spec.capability_names.get(m, m) for m in r.missing_capabilities))
        with c2:
            st.markdown(f"**Judge:** {ui.badge(p.validation.status, ui.VERDICT_COLOR[p.validation.status])}", unsafe_allow_html=True)
            st.caption(p.validation.judge_notes)
            st.markdown(f"**Adaptation (indicative):** {p.adaptation_effort_hours.estimate:.0f} h ({p.adaptation_effort_hours.confidence})")
            for label, items in [("Interfaces", p.interfaces), ("Deployment", p.deployment_constraints), ("Dependencies", p.dependencies[:8]),
                                 ("Known gaps", p.known_gaps), ("Risks", p.risks), ("Required modifications", r.required_modifications)]:
                if items:
                    st.markdown(f"**{label}**\n" + "\n".join(f"- {i}" for i in items))
        if p.evidence:
            st.markdown("**Evidence**")
            st.dataframe(pd.DataFrame([e.model_dump() for e in p.evidence]), width="stretch", hide_index=True)
        st.download_button("Passport JSON", p.model_dump_json(indent=2), f"{p.passport_id}.json", key=f"dl{p.passport_id}")
