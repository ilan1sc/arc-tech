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


VERSION = (ROOT / "VERSION").read_text().strip()


def version_footer():
    """App version, bottom of every page (bumped once per review round; see CHANGELOG.md)."""
    import subprocess
    try:
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             timeout=3).stdout.strip()
    except Exception:  # noqa: BLE001
        sha = ""
    st.markdown(f"""<div style="position:fixed;bottom:6px;right:14px;z-index:999;font-size:.75rem;color:#8a93a3;
        background:rgba(255,255,255,.85);padding:2px 8px;border-radius:8px">arc-tech v{VERSION}{' · ' + sha if sha else ''}</div>""",
                unsafe_allow_html=True)


def page(title: str, icon: str = "🛰️"):
    st.set_page_config(page_title=f"arc-tech · {title}", page_icon=icon, layout="wide")
    with st.sidebar:
        h = llm.health()
        st.caption("**arc-tech · Operation SwissLink** (fictional)")
        st.caption(f"Ollama: {h.get('mode')} {'✅' if h.get('ok') or h.get('mode') == 'live' else '⚠️'}")
        st.caption("Runs on DGX Spark · local Ollama · no data leaves the box except public GitHub/GitLab search terms")
    st.title(title)
    version_footer()


def model_selector(*roles: str):
    """Model picker for the engine(s) on this page + the independent judge. Changing a model re-runs live (cache is per model)."""
    models = llm.available_models()
    cols = st.columns(len(roles) + 1)
    for col, role in zip(cols, roles):
        cur = llm.MODELS[role]
        opts = models if cur in models else [cur] + models
        llm.MODELS[role] = col.selectbox(f"🧠 {llm.ROLE_LABELS[role]} model", opts, index=opts.index(cur), key=f"model_{role}",
                                         help="Results are cached per model: switching model runs the step live on the Spark.")
    cols[-1].caption(" ")
    cols[-1].caption("Judge = a separate model reviewing this engine's output (PASS / REVISE / BLOCK).")


def mermaid(src: str, height: int = 620, key: str = "m", zoom: float | None = None):
    """Render Mermaid from our own JSON-derived source; mermaid.js is served locally (works offline).
    Default = the whole diagram fitted into the frame (no inner scrollbars). Zoom > 1 enlarges it; only then the
    frame scrolls. securityLevel 'strict' sanitizes labels (they contain LLM-generated names)."""
    if zoom is None:
        zoom = st.slider("🔍 Zoom (1× = whole diagram)", 1.0, 4.0, 1.0, 0.25, key=f"zoom_{key}")
    esc = html.escape(src)
    st.iframe(f"""<!doctype html><html><body style="margin:0;background:white;overflow:hidden">
<div id="box" style="width:100%;height:{height - 8}px;overflow:{'auto' if zoom > 1 else 'hidden'};border:1px solid #ddd;
     border-radius:8px;display:flex;justify-content:center;align-items:flex-start">
  <pre class="mermaid" style="margin:0">{esc}</pre>
</div>
<script src="/app/static/mermaid.min.js"></script>
<script>
  mermaid.initialize({{startOnLoad:false, securityLevel:'strict', theme:'default',
    flowchart:{{htmlLabels:false, curve:'basis', nodeSpacing:28, rankSpacing:70, useMaxWidth:false}},
    themeVariables:{{fontSize:'15px'}}, maxTextSize: 200000}});
  mermaid.run().then(() => {{
    const svg = document.querySelector('pre.mermaid svg'), box = document.getElementById('box');
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    const fit = Math.min((box.clientWidth - 16) / r.width, (box.clientHeight - 16) / r.height, 1.6);
    const k = fit * {zoom};
    svg.style.maxWidth = 'none';
    svg.setAttribute('width', r.width * k); svg.setAttribute('height', r.height * k);
    if ({zoom} > 1) box.style.justifyContent = 'flex-start';
  }});
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
        a.reuse_adaptation_floor.base = st.slider("Reuse adaptation floor (% of BUILD)", 0.05, 0.6,
                                                   float(a.reuse_adaptation_floor.base), 0.05,
                                                   help="Minimum effort to adopt third-party software, relative to building it.")
        st.caption("All hour baselines are illustrative, editable assumptions — not measured costs.")
    return a


# ---------------------------------------------------------------- project / architecture selection
def current_arch_id() -> str | None:
    """The architecture (one per SRS) the whole app works on; chosen in the sidebar, kept across pages."""
    from engine2_architect import api as e2
    archs = e2.list_architectures()
    if not archs:
        return None
    ids = [d.architecture_id for d in archs]
    if st.session_state.get("arch_id") not in ids:
        st.session_state.arch_id = "ARCH-SWISSLINK" if "ARCH-SWISSLINK" in ids else ids[0]
    def first_title(d):
        v1 = e2.get_architecture(d.architecture_id, 1)
        return (v1.title if v1 and v1.title else d.architecture_id)
    labels = {d.architecture_id: f"{first_title(d)[:48]} · {d.source_name or 'SRS'}" for d in archs}
    st.sidebar.selectbox("📁 Project (SRS → architecture)", ids, key="arch_id", format_func=lambda i: labels[i],
                         help="Each SRS you load becomes its own project. Revisions (v2, v3…) live inside the project.")
    return st.session_state.arch_id


def version_label(d) -> str:
    """'v2 · Offline only' instead of a bare number."""
    entry = next((c for c in reversed(d.change_log) if c.version == d.version and not c.summary.startswith("Self-check")), None)
    import re
    m = re.search(r"User instruction: ([^;]+)", entry.reason) if entry else None
    what = "Initial architecture from the SRS" if d.version == 1 else (m.group(1) if m else (entry.summary if entry else "revision"))
    return f"v{d.version} · {what[:70]}"


def req_tip(rid: str, texts: dict[str, str]) -> str:
    """Requirement id with its full text on mouse-over."""
    t = html.escape(texts.get(rid, "unknown requirement"), quote=True)
    return (f"<abbr title=\"{t}\" style=\"text-decoration:underline dotted;cursor:help;"
            f"font-family:monospace;background:#eef2f8;padding:0 4px;border-radius:4px\">{html.escape(rid)}</abbr>")


def req_tips(ids, texts) -> str:
    return " ".join(req_tip(i, texts) for i in ids)


def read_srs_upload(f) -> str:
    """Text from an uploaded SRS (.md, .txt, .pdf, .docx)."""
    name = f.name.lower()
    data = f.getvalue()
    if name.endswith(".pdf"):
        import io
        from pypdf import PdfReader
        return "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        import io
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    return data.decode("utf-8", errors="replace")
