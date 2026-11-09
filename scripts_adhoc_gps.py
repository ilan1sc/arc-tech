"""Pre-run the PRD 1 demo: ad-hoc 'GPS tracking' matched to the tracking-capability owner (same slot logic as the UI)."""
import time
from engine1_explore import api as e1
from engine1_explore.rank import rank_component
from engine2_architect import api as e2
d = e2.get_architecture("ARCH-SWISSLINK")
specs = list(e2.get_component_requirements(d.architecture_id, d.version))
base = max(specs, key=lambda s: sum(c.startswith("CAP.TRACK") for c in s.required_capabilities))
q = "GPS tracking"
slug = "".join(ch if ch.isalnum() else "-" for ch in q.lower()).strip("-")
spec = base.model_copy(update={"search_terms": [q], "component_id": f"ADHOC-{base.component_id}-{slug}"})
t = time.time()
before = e1.load_exploration(base.component_id)
res = e1.explore_component(spec, queries=[q], keep=2, progress=lambda m: print("  >", m, flush=True))
print(f"{time.time()-t:.0f}s  stored as {spec.component_id}; matched against {base.component_id} {base.required_capabilities}")
pp = {p.passport_id: p for p in res.passports}
for r in rank_component(spec, res.passports):
    p = pp[r.candidate_id]
    print(f"  #{r.rank or '-'} {p.software_name} {p.license} score={r.total_score} judge={p.validation.status} missing={r.missing_capabilities}")
after = e1.load_exploration(base.component_id)
print("component slot untouched:", (before.model_dump() if before else None) == (after.model_dump() if after else None))
