"""Build the canonical demo chain (root -> maximize reuse -> offline only) and fill the cache."""
import time
from pathlib import Path
from engine3_optimize import orchestrator as e3
from engine3_optimize.effort import EffortAssumptions
a = EffortAssumptions()
t = time.time()
root = e3.start(Path("data/swisslink_srs.md").read_text(), a, explore=False)
r1 = e3.refine(root, "Too expensive; maximize reuse", a, progress=print)
r2 = e3.refine(r1, "Offline only", a, progress=print)
for it in (root, r1, r2):
    print(it.iteration_id, it.user_instruction, it.proposals,
          [(e.label.split(' (')[0], round(e.total_hours.base), f"{e.score_breakdown['reuse_share']:.0%}", e.feasible) for e in it.evaluations])
print(f"done in {time.time()-t:.0f}s")
