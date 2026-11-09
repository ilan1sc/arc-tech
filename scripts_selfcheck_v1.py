"""Apply the Engine 2 self-check to the published v1 in place (ids preserved)."""
import time
from collections import Counter
from shared import store
from engine2_architect import api as e2
t = time.time()
d = e2.get_architecture("ARCH-SWISSLINK", 1)
before = Counter(f.rule for f in d.validation_findings)
base = dict(architecture_id=d.architecture_id, version=1, requirements_revision=d.requirements_revision,
            requirements=d.requirements, open_questions=d.open_questions, capabilities=d.capabilities,
            constraints=d.constraints, change_log=d.change_log)
old_ids = {c.id for c in d.components}
d2 = e2.self_check(d, base)
store.save("architecture", d2.architecture_id, d2, version=1)
print("seconds", round(time.time() - t))
print("before", dict(before)); print("after ", dict(Counter(f.rule for f in d2.validation_findings)))
print("components kept", len(old_ids & {c.id for c in d2.components}), "/", len(old_ids), "new", {c.id for c in d2.components} - old_ids)
print("interfaces", len(d.interfaces), "->", len(d2.interfaces))
print("gaps", [c.requirement_id for c in d2.coverage if c.status == "gap"])
for c in d2.change_log: print(" ", c.summary[:140])
