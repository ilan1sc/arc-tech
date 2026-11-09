"""Background batch: Engine 1 explores every Engine 2 component (fills the cache for the demo)."""
import sys
import time

from engine1_explore import api as e1
from engine2_architect import api as e2

keep = int(sys.argv[1]) if len(sys.argv) > 1 else 2
d = e2.get_architecture("ARCH-SWISSLINK")
t0 = time.time()
for spec in e2.get_component_requirements(d.architecture_id, d.version):
    if e1.load_exploration(spec.component_id):
        print("skip (cached)", spec.component_id, flush=True)
        continue
    t = time.time()
    res = e1.explore_component(spec, keep=keep, progress=lambda m: print("   ", m, flush=True))
    top = res.shortlist(1)
    print(f"{spec.component_id}: {len(res.discovered)} found, {len(res.passports)-1} passports, "
          f"top={top[0].candidate_id if top else '-'} {top[0].total_score if top else ''}, "
          f"errors={len(res.errors)} [{time.time()-t:.0f}s]", flush=True)
print(f"done in {time.time()-t0:.0f}s")
