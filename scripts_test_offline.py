import time
from engine3_optimize import orchestrator as e3
from engine3_optimize.effort import EffortAssumptions
t = time.time()
parent = e3.load_iteration("IT-2754E1")
it = e3.refine(parent, "Offline only", EffortAssumptions(), progress=lambda m: print("  >", m, flush=True))
print("secs", round(time.time() - t), it.iteration_id, it.proposals)
print("constraints", it.constraints)
for c in it.changes: print(" change:", c[:220])
for c in it.critique: print(" critique:", c[:260])
for ev in it.evaluations:
    print(f"   {ev.label}: base {ev.total_hours.base:,.0f} h reuse {ev.score_breakdown['reuse_share']:.0%} feasible={ev.feasible} "
          f"violations={ev.hard_gate_violations} unknown={len(ev.unknown_estimates)}")
