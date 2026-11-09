import ui  # noqa: F401  (sets sys.path)
import streamlit as st

from engine2_architect import api as e2
from engine3_optimize import orchestrator as e3
from shared import store

ui.page("How it works — three engines", "🧭")
st.markdown("""
Three independent engines with shared JSON contracts, running locally on the DGX Spark:

| Engine | PRD | Owns | Does **not** |
|---|---|---|---|
| **1 · Software Exploration** | PRD 1 v0.3 | GitHub + GitLab discovery, Capability Passports, suitability ranking | choose Build/Buy/Reuse |
| **2 · Architecture Generator** | PRD 2 v0.3 | SRS → requirements → capabilities → **one** logical architecture, validation, revisions | pick products, estimate cost |
| **3 · Optimizer** | PRD 3 v0.2 | orchestration, Build/Buy/Reuse, hours & money overlays, chat iterations | promise schedules or headcount |

An independent LLM judge validates passports, rankings and architectures (PASS / REVISE / BLOCK).
""")

d = e2.get_architecture("ARCH-SWISSLINK")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Architecture versions", len(e2.list_versions("ARCH-SWISSLINK")))
c2.metric("Components", len(d.components) if d else 0)
c3.metric("Passports", len(store.list_ids("passport")))
c4.metric("Iterations", len(e3.list_iterations()))

st.subheader("5-minute demo")
st.markdown("""
1. **Requirements** — load SwissLink SRS, show extracted requirements, open questions and the capability tree.
2. **Exploration** — search *"GPS tracking"*, inspect a repository, produce a passport, match to SwissLink force tracking → **missing persistent history** shows as a gap.
3. **Architecture** — the single Engine 2 architecture, click a component for details, toggle **Hours / Money** overlays.
4. **Optimizer** — architectures A/B/C (Balanced / Max reuse / Build-heavy), per-component and per-architecture comparison.
5. **Chat** — *"Too expensive; maximize reuse"* → new iteration with explanation; *"offline only"* → Engine 2 revision v2 with diff.
""")
st.info("Everything here is fictional. Estimates are editable assumptions, never measured costs. Unknown is shown as unknown, never zero.")
