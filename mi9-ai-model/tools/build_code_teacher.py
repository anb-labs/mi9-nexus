#!/usr/bin/env python3
"""Build teacher traces for CODE families (the fenced format).

Every teacher trace so far was <answer>-shaped, so training drifted toward
wrapping code in <answer> too. Code prompts ask for a ```python block plus the
literal <answer>DONE</answer>, so code traces must be built that way or the
model learns the wrong serving format.

Serves as a template too: tasks carry a `reference` solution, which the
verifier executes against the task's tests.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nexus import tasks  # noqa: E402
from nexus.selfplay import SOLVER_SYSTEM  # noqa: E402

OUT = ROOT / "data" / "teacher-code-batch.json"
DIFFICULTIES = [3, 4]

code_fams = [f for f in tasks.FAMILIES
             if (t := tasks.generate(f, 3, seed=11))
             and t["domain"] == "code" and t.get("reference")]

batch = []
for fam in code_fams:
    for d in DIFFICULTIES:
        t = tasks.generate(fam, d, seed=11)
        if not t or not t.get("reference"):
            continue
        final = f"```python\n{t['reference'].strip()}\n```\n<answer>DONE</answer>"
        batch.append({
            "task_id": t["id"], "family": t["family"], "domain": t["domain"],
            "difficulty": t["difficulty"], "prompt": t["prompt"],
            "spec": t["spec"], "answer": t["answer"], "kind": t["kind"],
            "trace": [
                {"role": "system", "content": SOLVER_SYSTEM},
                {"role": "user", "content": t["prompt"]},
                {"role": "assistant", "content": final},
            ],
        })

json.dump(batch, open(OUT, "w"), indent=1)
print(f"code teacher traces built: {len(batch)} across "
      f"{len({b['family'] for b in batch})} families -> {OUT}")
