"""Evaluation harness (whitepaper Phase 0 deliverable, scaled to micro).

Two locked suites, frozen on disk, never regenerated after the fact:
  - frozen.json: held-out capability probe, EVAL_PER_FAMILY tasks per family
  - regression.json: the rollback gate for nightly adapters (Ch. 6.5)

Both are self-generated with random parameters, so only the executor knows
the answers: benchmark contamination is structurally impossible (Ch. 6.4).
"""
import argparse
import datetime
import json
import os
import subprocess
import time
import urllib.request

from . import config, client, sandbox, tasks
from . import answer as A
from .selfplay import run_task, load_json


# Families whose prompts instruct a tool call (run_python / retrieve) rather
# than a ```python fence — these must be scored through the agentic loop.
# (file_ops / dataframe ask for a code fence and go through single-shot run_task.)
TOOL_FAMILIES = {"math_exec", "retrieval_qa"}


class TemporaryServer:
    """Start llama-server with a candidate LoRA on a private port (gate use)."""

    def __init__(self, adapter, port=8091):
        self.port, self.adapter = port, adapter
        self.proc = None

    def _url(self):
        return f"http://{config.SERVER_HOST}:{self.port}"

    def __enter__(self):
        cmd = ["llama-server", "-m", str(config.BASE_MODEL),
               "--host", config.SERVER_HOST, "--port", str(self.port),
               "--ctx-size", "4096", "--threads", "8", "--jinja",
               "--lora", self.adapter]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                urllib.request.urlopen(self._url() + "/health", timeout=2)
                break
            except Exception:
                if self.proc.poll() is not None:
                    raise SystemExit("candidate server failed to start")
                time.sleep(1)
        old = config.SERVER_PORT
        config.SERVER_PORT = self.port
        import importlib
        global client
        config.SERVER_URL = f"http://{config.SERVER_HOST}:{self.port}"
        self._old_port = old
        return self

    def __exit__(self, *a):
        config.SERVER_PORT = self._old_port
        config.SERVER_URL = f"http://{config.SERVER_HOST}:{self._old_port}"
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=20)


def build_suite(n_per_family, seed, difficulty, families=None):
    suite = []
    for fam in (families or tasks.FAMILIES):
        made, tries = 0, 0
        while made < n_per_family and tries < n_per_family * 6:
            tries += 1
            t = tasks.generate(fam, difficulty, seed=seed + tries * 977 + made)
            if t is None:
                continue
            suite.append({k: t[k] for k in ("id", "family", "domain", "difficulty",
                                            "kind", "prompt", "spec")})
            made += 1
    return suite


def freeze():
    frozen = build_suite(config.EVAL_PER_FAMILY, seed=20260101, difficulty=3)
    reg = build_suite(max(1, config.REGRESSION_SIZE // len(tasks.FAMILIES)),
                      seed=19991225, difficulty=2)
    # capability suite: the new families (file_ops, retrieval_qa, math_exec)
    # at d3-d5 + the original families pushed to d6-d8. Measures what the
    # regression suite can't: newly learned skills and harder difficulties.
    cap = []
    for fam in ("file_ops", "retrieval_qa", "math_exec"):
        cap += build_suite(8, seed=777, difficulty=3, families=[fam])
        cap += build_suite(4, seed=778, difficulty=5, families=[fam])
    hard = build_suite(4, seed=779, difficulty=7,
                       families=[f for f in tasks.FAMILIES
                                 if f not in ("file_ops", "retrieval_qa", "math_exec")])
    cap += hard
    json.dump(frozen, open(config.SUITES / "frozen.json", "w"))
    json.dump(reg, open(config.SUITES / "regression.json", "w"))
    json.dump(cap, open(config.SUITES / "capability.json", "w"))
    print(f"frozen: {len(frozen)} tasks -> {config.SUITES/'frozen.json'}")
    print(f"regression: {len(reg)} tasks -> {config.SUITES/'regression.json'}")
    print(f"capability: {len(cap)} tasks -> {config.SUITES/'capability.json'}")


def score_task(t, temperature=0.7, think=False):
    t0 = time.time()
    try:
        if t.get("family") in TOOL_FAMILIES:
            # tool-augmented families are designed to be solved with the ReAct
            # tool loop (emit run_python / retrieve, then answer). Scoring them
            # single-shot (which needs a ```python fence they never emit) makes
            # them ~0% by construction — route them through the agentic loop.
            from . import agentic
            msgs, got, verdict = agentic.run_agentic(
                t, temperature=temperature, max_rounds=4)
        else:
            raw, got, verdict = run_task(t, temperature=temperature, think=think)
    except Exception as e:
        return {"id": t["id"], "family": t["family"], "domain": t["domain"],
                "correct": False,
                "error": str(e)[:200], "seconds": round(time.time() - t0, 1)}
    return {"id": t["id"], "family": t["family"], "domain": t["domain"],
            "difficulty": t["difficulty"], "correct": bool(verdict.get("ok")),
            "error": verdict.get("error"), "seconds": round(time.time() - t0, 1)}


def run_suite(path, k=1, temperature=0.7, label="eval", adapter=None, test_time=False):
    if adapter:
        with TemporaryServer(adapter):
            return _run_suite_inner(path, k, temperature, label, test_time)
    return _run_suite_inner(path, k, temperature, label, test_time)


def _run_suite_inner(path, k, temperature, label, test_time=False):
    if not client.health():
        raise SystemExit("llama-server is not up (nexus serve start)")
    suite = json.load(open(path))
    results = []
    t0 = time.time()
    for i, t in enumerate(suite, 1):
        if test_time:
            # best-of-k with executor verification (test-time compute)
            from . import infer
            ans, verdict, n = infer.solve_verified(t, k=k, temperature=temperature)
            correct = bool(verdict.get("ok"))
            results.append({"id": t["id"], "family": t["family"],
                            "domain": t["domain"], "difficulty": t.get("difficulty"),
                            "correct": correct, "error": verdict.get("error"),
                            "seconds": 0, "samples": n})
        else:
            verdicts = [score_task(t, temperature=temperature) for _ in range(k)]
            correct = any(v["correct"] for v in verdicts)
            results.append({**verdicts[0], "correct": correct, "samples": k})
        done = i / (time.time() - t0)
        eta = (len(suite) - i) / done if done > 0 else 0
        print(f"[{i:3d}/{len(suite)}] {t['family']:18s} {'PASS' if correct else 'FAIL'} "
              f"(eta {eta:5.0f}s)", flush=True)
    by_fam = {}
    for r in results:
        f = by_fam.setdefault(r["family"], {"pass": 0, "n": 0})
        f["pass"] += r["correct"]
        f["n"] += 1
    overall = sum(r["correct"] for r in results) / max(1, len(results))
    dom = {}
    for r in results:
        d = dom.setdefault(r["domain"], [0, 0])
        d[1] += 1
        d[0] += r["correct"]
    report = {
        "label": label, "suite": str(path), "when": datetime.datetime.now().isoformat(),
        "overall_pass1": round(overall, 4), "domains": {k: round(v[0] / v[1], 3) for k, v in dom.items()},
        "by_family": {k: round(v["pass"] / v["n"], 3) for k, v in sorted(by_fam.items())},
        "results": results,
    }
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = config.REPORTS / f"{label}-{stamp}.json"
    json.dump(report, open(out, "w"), indent=1)
    print(f"\n== {label}: pass@1 overall {overall*100:.1f}% "
          f"(math {dom.get('math',[0,0]) and round(dom['math'][0]/dom['math'][1]*100,1)}%, "
          f"code {dom.get('code',[0,0]) and round(dom['code'][0]/dom['code'][1]*100,1)}%, "
          f"logic {dom.get('logic',[0,0]) and round(dom['logic'][0]/dom['logic'][1]*100,1)}%)")
    print(f"report: {out}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["freeze", "run"])
    ap.add_argument("--suite", default="frozen",
                    choices=["frozen", "regression", "capability"])
    ap.add_argument("--k", type=int, default=config.K_SAMPLES)
    ap.add_argument("--label", default="eval")
    ap.add_argument("--adapter", default=None, help="LoRA gguf to serve for this eval")
    ap.add_argument("--test-time", action="store_true",
                    help="best-of-k with executor verification (test-time compute)")
    args = ap.parse_args()
    if args.cmd == "freeze":
        freeze()
    else:
        path = config.SUITES / f"{args.suite}.json"
        run_suite(path, k=args.k, label=args.label, adapter=args.adapter,
                  test_time=args.test_time)


if __name__ == "__main__":
    main()
