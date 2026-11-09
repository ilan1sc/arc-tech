"""Opening slide of the demo: the pain."""
import ui  # noqa: F401  (sets sys.path)
import streamlit as st

st.set_page_config(page_title="arc-tech · The problem", page_icon="🛰️", layout="wide", initial_sidebar_state="collapsed")
ui.version_footer()

st.markdown("""
<style>
  .block-container {padding-top: 4rem; max-width: 1250px;}
  .eyebrow {letter-spacing: .18em; font-weight: 700; font-size: .85rem; color: #c0392b; margin-bottom: .4rem;}
  .headline {font-size: 2.55rem; line-height: 1.18; font-weight: 800; color: #1d2433; margin: 0 0 1.4rem 0;}
  .headline em {font-style: normal; color: #c0392b;}
  .flow {display: flex; align-items: stretch; gap: .5rem; margin: .6rem 0 .3rem 0;}
  .step {flex: 1; background: #f4f6fa; border: 1px solid #dfe3eb; border-radius: 12px; padding: .8rem .9rem;}
  .step b {display: block; font-size: 1.02rem; color: #1d2433;}
  .step span {font-size: .86rem; color: #5b6475;}
  .arrow {align-self: center; font-size: 1.5rem; color: #9aa3b2;}
  .bar {position: relative; height: 34px; margin: .35rem 0 1.6rem 0; border-radius: 8px;
        background: repeating-linear-gradient(45deg, #fde2e1, #fde2e1 10px, #fbd3d1 10px, #fbd3d1 20px);
        border: 1px solid #f0b4b0; display: flex; align-items: center; justify-content: center;
        font-weight: 700; color: #a3281c; font-size: .98rem;}
  .cards {display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;}
  .card {background: white; border: 1px solid #e3e6ee; border-top: 5px solid #c0392b; border-radius: 12px;
         padding: 1.05rem 1.05rem 1.15rem 1.05rem; box-shadow: 0 2px 10px rgba(20,30,60,.05);}
  .card .icon {font-size: 1.9rem;}
  .card h4 {margin: .35rem 0 .45rem 0; font-size: 1.12rem; color: #1d2433;}
  .card p {margin: 0; font-size: .93rem; line-height: 1.42; color: #4a5263;}
  .whatif {margin-top: 1.8rem; padding: 1.05rem 1.3rem; border-radius: 12px; background: #1d2433; color: #fff;
           font-size: 1.28rem; font-weight: 600;}
  .whatif em {font-style: normal; color: #7ee2a8;}
  @media (max-width: 900px) {.cards {grid-template-columns: 1fr 1fr;} .flow {flex-direction: column;} .arrow {display:none;}
                             .headline {font-size: 1.8rem;}}
</style>

<div class="eyebrow">THE PROBLEM</div>
<div class="headline">Every new project starts with <em>a month of architecture guesswork</em> —
and we still end up rebuilding software that already exists.</div>

<div class="flow">
  <div class="step"><b>📄 Software Requirements Specification</b><span>A new project or proposal kicks off</span></div>
  <div class="arrow">→</div>
  <div class="step"><b>🏗️ Architecture</b><span>Components, interfaces, data, security</span></div>
  <div class="arrow">→</div>
  <div class="step"><b>⚖️ Build · Buy · Reuse</b><span>A decision for every component</span></div>
  <div class="arrow">→</div>
  <div class="step"><b>💰 Cost &amp; proposal</b><span>Effort, money, risk</span></div>
</div>
<div class="bar">≈ 1 month · manual · senior engineers · little evidence</div>

<div class="cards">
  <div class="card"><div class="icon">🕐</div><h4>A month of architecture work</h4>
    <p>Before a proposal can even be costed, senior engineers spend weeks turning requirements into an architecture.</p></div>
  <div class="card"><div class="icon">🔍</div><h4>Existing software is invisible</h4>
    <p>Reusable components are scattered across internal repositories and open source — hard to find, hard to trust, hard to compare.</p></div>
  <div class="card"><div class="icon">🧱</div><h4>We default to “build”</h4>
    <p>Without time to evaluate alternatives, teams build from scratch and pay again for capabilities they already own.</p></div>
  <div class="card"><div class="icon">💸</div><h4>Decisions without evidence</h4>
    <p>Build / buy / reuse calls and cost estimates rest on gut feeling — not on what the software actually does.</p></div>
</div>

<div class="whatif">What if requirements → architecture → build/buy/reuse → cost took <em>minutes instead of a month</em>,
with evidence behind every decision?</div>
""", unsafe_allow_html=True)

st.write("")
c1, c2, _ = st.columns([1.2, 1.2, 4])
c1.page_link("pages/0_Overview.py", label="How it works →", icon="🧭")
c2.page_link("pages/1_Requirements.py", label="Start the demo →", icon="▶️")
