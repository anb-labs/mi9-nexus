"""Test-time-compute gain on the tool-augmented families (the frontier-adjacent
skills: math_exec, file_ops, dataframe). pass@1 vs best-of-k with verification."""
import json, sys, time
from nexus import infer

suite = json.load(open("suites/capability.json"))
fams = ["math_exec", "file_ops", "dataframe"]
sample = []
for f in fams:
    sample += [t for t in suite if t["family"] == f][:3]

k = int(sys.argv[1]) if len(sys.argv) > 1 else 5
p1 = pk = 0
t0 = time.time()
for i, t in enumerate(sample, 1):
    a1, v1, _ = infer.solve_verified(t, k=1)
    ak, vk, n = infer.solve_verified(t, k=k)
    p1 += bool(v1.get("ok"))
    pk += bool(vk.get("ok"))
    print(f"[{i}/{len(sample)}] {t['family']:12s} pass@1={int(v1.get('ok'))} "
          f"best@{k}={int(vk.get('ok'))} (tried {n}) {time.time()-t0:.0f}s", flush=True)
print(f"\n== tool families: pass@1 {p1}/{len(sample)} = {p1/len(sample)*100:.0f}%  |  "
      f"best@{k} {pk}/{len(sample)} = {pk/len(sample)*100:.0f}%")