"""Shared Streamlit helpers."""
from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from shared import llm  # noqa: E402
from shared.schemas import EffortRange  # noqa: E402

SRS_PATH = ROOT / "data" / "swisslink_srs.md"


def page(title: str, icon: str = "🛰️"):
    st.set_page_config(page_title=f"arc-tech · {title}", page_icon=icon, layout="wide")
    with st.sidebar:
        h = llm.health()
        st.caption("**arc-tech · Operation SwissLink** (fictional)")
        st.caption(f"LLM: `{h.get('model')}` — {h.get('mode')} {'✅' if h.get('ok') else '⚠️'}")
        st.caption("Runs on DGX Spark · local Ollama · no data leaves the box except public GitHub/GitLab search terms")
    st.title(title)


def mermaid(src: str, height: int = 720, key: str = "m", zoom: float | None = None):
    """Render Mermaid from our own JSON-derived source. mermaid.js is served locally (/app/static), works offline.
    securityLevel 'strict' sanitizes labels (they contain LLM-generated names)."""
    if zoom is None:
        zoom = st.slider("Diagram zoom", 0.3, 1.5, 0.55, 0.05, key=f"zoom_{key}")
    esc = html.escape(src)
    st.iframe(f"""<!doctype html><html><body style="margin:0;background:white">
<div style="width:100%;height:{height - 12}px;overflow:auto;border:1px solid #ddd;border-radius:8px">
  <pre class="mermaid" style="margin:0;zoom:{zoom}">{esc}</pre>
</div>
<script src="/app/static/mermaid.min.js"></script>
<script>
  mermaid.initialize({{startOnLoad:true, securityLevel:'strict', theme:'default',
    flowchart:{{htmlLabels:true, curve:'basis', nodeSpacing:28, rankSpacing:70, useMaxWidth:false}}, themeVariables:{{fontSize:'15px'}}, maxTextSize: 200000}});
</script></body></html>""", height=height)


def fmt(r: EffortRange | None, unit: str = "h", money: bool = False, currency: str = "") -> str:
    if r is None or not r.known:
        return "unknown"
    if money:
        f = lambda v: f"{v:,.0f}"
        return f"{currency} {f(r.low)} – {f(r.high)} (base {f(r.base)})"
    return f"{r.low:,.0f} – {r.high:,.0f} {unit} (base {r.base:,.0f})"


def badge(text: str, color: str) -> str:
    return f"<span style='background:{color};padding:2px 8px;border-radius:10px;font-size:0.8em'>{text}</span>"


STATUS_COLOR = {"verified": "#c8e6c9", "declared": "#bbdefb", "inferred": "#fff9c4", "unknown": "#eeeeee"}
VERDICT_COLOR = {"PASS": "#c8e6c9", "REVISE": "#fff9c4", "BLOCK": "#ffcdd2", "passed": "#c8e6c9", "pending": "#fff9c4", "failed": "#ffcdd2"}
DECISION_COLOR = {"BUILD": "#fde2e1", "BUY": "#e1ecfd", "REUSE": "#e3f6e5"}


def assumptions_editor():
    """Editable effort/money assumptions kept in session state."""
    from engine3_optimize.effort import EffortAssumptions
    if "assumptions" not in st.session_state:
        st.session_state.assumptions = EffortAssumptions()
    a = st.session_state.assumptions
    with st.sidebar.expander("💰 Cost assumptions (editable)", expanded=False):
        a.currency = st.text_input("Currency", a.currency)
        a.hourly_rate = st.number_input("Loaded hourly rate", 10.0, 1000.0, float(a.hourly_rate), 5.0,
                                        help="Changing the rate recomputes money; hours stay the same.")
        a.risk_reserve_fraction = st.slider("Risk reserve", 0.0, 0.5, float(a.risk_reserve_fraction), 0.05)
        st.caption("All hour baselines are illustrative, editable assumptions — not measured costs.")
    return a
