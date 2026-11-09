"""Mermaid rendering from the single ArchitectureDesign JSON (+ optional Engine 3 overlay)."""
from __future__ import annotations

import re
from typing import Literal, Optional

from shared.schemas import ArchitectureDesign, EffortRange, Overlay

DECISION_CLASS = {"BUILD": "build", "BUY": "buy", "REUSE": "reuse"}


def _nid(x: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", x)


def _esc(s: str) -> str:
    return s.replace('"', "'").replace("[", "(").replace("]", ")")


def fmt_range(r: EffortRange, unit: str = "h", money: bool = False) -> str:
    if not r.known:
        return "unknown"
    f = (lambda v: f"{v/1000:,.0f}k") if money and (r.base or 0) >= 10_000 else (lambda v: f"{v:,.0f}")
    return f"{f(r.low)}–{f(r.high)}{unit}" if r.low is not None and r.high is not None else f"{f(r.base)}{unit}"


def render(design: ArchitectureDesign, overlay: Optional[Overlay] = None,
           mode: Literal["none", "hours", "money"] = "none", currency: str = "$",
           highlight: Optional[set[str]] = None) -> str:
    highlight = highlight or set()
    lines = ["flowchart LR"]
    by_sub: dict[str, list] = {}
    for c in design.components:
        by_sub.setdefault(c.subsystem or "Core", []).append(c)

    def label(node_id: str, name: str) -> str:
        extra = ""
        if overlay and mode != "none":
            v = overlay.nodes.get(node_id)
            if v is None:
                extra = "<br/>unknown"
            else:
                tag = f"{v.decision} · " if v.decision else ""
                extra = f"<br/>{tag}" + (fmt_range(v.hours, 'h') if mode == "hours" else fmt_range(v.money, '', True) + f" {currency}")
        return f'"{_esc(name)}<br/>{node_id}{extra}"'

    stores_by_owner: dict[str, list] = {}
    for ds in design.data_stores:
        stores_by_owner.setdefault(ds.owner_component, []).append(ds)
    for i, (sub, comps) in enumerate(by_sub.items()):
        lines.append(f'  subgraph SG{i}["{_esc(sub)}"]')
        for c in comps:
            shape = ("([", "])") if c.kind in ("ui", "client_app") else ("[", "]")
            lines.append(f"    {_nid(c.id)}{shape[0]}{label(c.id, c.name)}{shape[1]}")
            for ds in stores_by_owner.get(c.id, []):
                lines.append(f'    {_nid(ds.id)}[("{_esc(ds.name)}<br/>{ds.id}")]')
        lines.append("  end")
    for ds in design.data_stores:
        lines.append(f"  {_nid(ds.owner_component)} --- {_nid(ds.id)}")
    if design.external_systems:
        lines.append('  subgraph EXT["External systems"]')
        for e in design.external_systems:
            tag = " (fictional)" if e.fictional else ""
            lines.append(f'    {_nid(e.id)}{{{{"{_esc(e.name)}{tag}"}}}}')
        lines.append("  end")
    for itf in design.interfaces:
        lab = _esc(itf.name)
        if overlay and mode != "none":
            v = overlay.edges.get(itf.id)
            lab += " · " + ("unknown" if v is None else (fmt_range(v.hours, 'h') if mode == "hours" else fmt_range(v.money, '', True) + f" {currency}"))
        arrow = "-.->" if itf.mode in ("async", "stream") else "-->"
        lines.append(f'  {_nid(itf.source)} {arrow}|"{lab}"| {_nid(itf.target)}')
    # styles
    lines += ["  classDef build fill:#fde2e1,stroke:#c0392b,color:#222",
              "  classDef buy fill:#e1ecfd,stroke:#2c5aa0,color:#222",
              "  classDef reuse fill:#e3f6e5,stroke:#2e7d32,color:#222",
              "  classDef hl stroke:#ff9800,stroke-width:4px"]
    if overlay:
        for nid, v in overlay.nodes.items():
            if v.decision:
                lines.append(f"  class {_nid(nid)} {DECISION_CLASS[v.decision]}")
    for h in highlight:
        lines.append(f"  class {_nid(h)} hl")
    return "\n".join(lines)
