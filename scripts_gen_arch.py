import time, json
from pathlib import Path
from engine2_architect.api import generate_architecture, get_component_requirements
t = time.time()
srs = Path("data/swisslink_srs.md").read_text()
d = generate_architecture(srs)
print("seconds", round(time.time() - t))
print(len(d.requirements), "reqs", len(d.open_questions), "OQs", len(d.capabilities), "caps",
      len(d.components), "comps", len(d.interfaces), "ifs", len(d.data_stores), "stores")
print("gaps", [c.requirement_id for c in d.coverage if c.status == "gap"])
from collections import Counter
print(Counter(f.severity for f in d.validation_findings))
for f in d.validation_findings:
    if f.severity in ("critical", "high"): print(" ", f.severity, f.message)
for c in d.components: print(c.id, "|", c.name, "|", c.subsystem)
print(len(get_component_requirements(d.architecture_id)), "specs")
