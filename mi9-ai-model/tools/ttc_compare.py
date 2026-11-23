"""Quick pass@1 vs best-of-k comparison to demonstrate test-time compute gain."""
import json, sys, time
from nexus import infer

suite = json.load(open("suites/regression.json"))
# sample: 2 tasks from each of 6 families (mix of code + text)
fams = ["reverse_string", "sum_ints", "gcd_lcm", "arith_chain", "bool_expr", "closure"]
sample = []
for f in fams:
    sample += [t for t in suite if t["family"] == f][:2]

k = int(sys.argv[1]) if len(sys.argv) > 1 else 5
p1 = pk = 0
t0 = time.time()
for i, t in enumerate(sample, 1):
    a1, v1, _ = infer.solve_verified(t, k=1)
    ak, vk, n = infer.solve_verified(t, k=k)
    p1 += bool(v1.get("ok"))
    pk += bool(vk.get("ok"))
    print(f"[{i}/{len(sample)}] {t['family']:16s} pass@1={int(v1.get('ok'))} "
          f"best@{k}={int(vk.get('ok'))} (tried {n}) {time.time()-t0:.0f}s", flush=True)
print(f"\n== pass@1 {p1}/{len(sample)} = {p1/len(sample)*100:.0f}%  |  "
      f"best@{k} {pk}/{len(sample)} = {pk/len(sample)*100:.0f}%")