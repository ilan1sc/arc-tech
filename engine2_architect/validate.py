"""AR-06 deterministic validation and coverage computation (no LLM)."""
from __future__ import annotations

from collections import defaultdict

from shared.schemas import ArchitectureDesign, CoverageEntry, ValidationFinding

VENDOR_WORDS = ["kafka", "postgres", "postgis", "mongodb", "redis", "elastic", "aws", "azure", "gcp", "firebase",
                "openlayers", "leaflet", "yolo", "rabbitmq", "mqtt broker mosquitto", "kubernetes"]


def compute_coverage(d: ArchitectureDesign) -> list[CoverageEntry]:
    alloc = defaultdict(list)
    for c in d.components:
        for rid in c.requirement_ids:
            alloc[rid].append(c.id)
    # requirements reached through capabilities a component claims
    cap_reqs = {cap.id: cap.requirement_ids for cap in d.capabilities}
    for c in d.components:
        for cap in c.required_capabilities:
            for rid in cap_reqs.get(cap, []):
                if c.id not in alloc[rid]:
                    alloc[rid].append(c.id)
    out = []
    system_wide = [c.id for c in d.components]
    for r in d.requirements:
        comps = alloc.get(r.id, [])
        if not comps and r.kind == "constraint":
            out.append(CoverageEntry(requirement_id=r.id, component_ids=system_wide, status="covered",
                                     note="System-wide constraint: applies to every component"))
            continue
        out.append(CoverageEntry(requirement_id=r.id, component_ids=comps,
                                 status="covered" if comps else "gap",
                                 note="" if comps else f"{r.priority} requirement not allocated to any component"))
    return out


def validate(d: ArchitectureDesign) -> list[ValidationFinding]:
    f: list[ValidationFinding] = []
    n = 0

    def add(sev, rule, msg, refs=()):
        nonlocal n
        n += 1
        f.append(ValidationFinding(id=f"VF-{n:03d}", severity=sev, rule=rule, message=msg, refs=list(refs)))

    comp_ids = {c.id for c in d.components}
    ext_ids = {e.id for e in d.external_systems}
    store_ids = {s.id for s in d.data_stores}
    endpoints = comp_ids | ext_ids | store_ids
    req_ids = {r.id for r in d.requirements}
    cap_ids = {c.id for c in d.capabilities}

    # unique ids
    seen = set()
    for x in [*comp_ids, *ext_ids, *store_ids, *(i.id for i in d.interfaces)]:
        if x in seen:
            add("critical", "unique-ids", f"Duplicate id {x}", [x])
        seen.add(x)
    # graph integrity
    for i in d.interfaces:
        for end in (i.source, i.target):
            if end not in endpoints:
                add("critical", "dangling-endpoint", f"Interface {i.id} references unknown endpoint '{end}'", [i.id])
        if i.source == i.target:
            add("medium", "self-loop", f"Interface {i.id} connects {i.source} to itself", [i.id])
    for c in d.components:
        for dep in c.dependencies:
            if dep not in endpoints:
                add("high", "dangling-dependency", f"{c.id} depends on unknown '{dep}'", [c.id])
        for rid in c.requirement_ids:
            if rid not in req_ids:
                add("high", "dangling-requirement", f"{c.id} references unknown requirement {rid}", [c.id])
        for cap in c.required_capabilities + c.optional_capabilities:
            if cap not in cap_ids:
                add("medium", "dangling-capability", f"{c.id} references unknown capability {cap}", [c.id])
        if not c.requirement_ids and not c.required_capabilities:
            add("medium", "untraced-component", f"{c.id} has no requirement or capability trace", [c.id])
        connected = any(c.id in (i.source, i.target) for i in d.interfaces)
        if not connected:
            add("medium", "isolated-component", f"{c.id} has no interfaces", [c.id])
        text = " ".join([c.name, c.purpose, *c.responsibilities]).lower()
        for v in VENDOR_WORDS:
            if v in text:
                add("low", "implementation-neutral", f"{c.id} mentions '{v}'; components should be implementation-neutral", [c.id])
    # data ownership
    for s in d.data_stores:
        if s.owner_component not in comp_ids:
            add("high", "data-ownership", f"Data store {s.id} owner '{s.owner_component}' is not a component", [s.id])
    # dependency cycles among components (sync calls only matter, but report all)
    graph = defaultdict(set)
    for c in d.components:
        for dep in c.dependencies:
            if dep in comp_ids:
                graph[c.id].add(dep)
    state: dict[str, int] = {}

    def dfs(u, stack):
        state[u] = 1
        for v in graph[u]:
            if state.get(v) == 1:
                cyc = stack[stack.index(v):] + [v]
                add("low", "dependency-cycle", "Dependency cycle: " + " -> ".join(cyc), cyc)
            elif not state.get(v):
                dfs(v, stack + [v])
        state[u] = 2
    for u in list(graph):
        if not state.get(u):
            dfs(u, [u])
    # coverage
    for ce in d.coverage:
        if ce.status == "gap":
            r = next(r for r in d.requirements if r.id == ce.requirement_id)
            add("critical" if r.priority == "mandatory" else "medium", "requirement-allocation",
                f"{r.id} ({r.priority}) is not allocated to any component", [r.id])
    # security / nonfunctional gaps surfaced, not certified
    if not any(i.security for i in d.interfaces):
        add("high", "interface-security", "No interface states security considerations")
    for r in d.requirements:
        if r.ambiguity:
            add("info", "ambiguous-requirement", f"{r.id}: {r.ambiguity}", [r.id])
    return f
