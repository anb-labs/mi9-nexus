"""Teacher distillation: frontier-model traces -> executor-verified -> replay buffer.

The teacher (a frontier model through an API) writes solutions for tasks;
the sandbox verifies each one; verified traces enter the replay buffer for
the student (1.7B) to distill. The teacher's supervision is far above the
student's self-play -- this is the "ML Without Data" recipe (teacher
generates -> rule-based validators curate -> student distills).

Flow:
  1. gen: generate a batch of tasks (weak families) and print the prompts
  2. (teacher writes solutions in the conversation)
  3. verify: sandbox-verify each solution; verified ones -> replay.jsonl

The task specs carry the ground truth (the generator computed it), so the
verifier is exact -- nothing unverified enters the buffer.
"""
import argparse
import json
import sys

from . import answer as A
from . import config
from . import sandbox
from . import tasks

TEACHER_SYSTEM = (
    "You are a precise reasoning assistant. Follow the task's output format "
    "exactly: code tasks want a single ```python block defining the required "
    "function; other tasks want <answer>...</answer>. No extra prose."
)


def gen(args):
    fams = args.families.split(",")
    batch = []
    for fam in fams:
        for i in range(args.n):
            t = tasks.generate(fam, args.difficulty, seed=args.seed + i * 131)
            if t is None:
                continue
            batch.append({
                "task_id": t["id"], "family": t["family"],
                "domain": t["domain"], "difficulty": t["difficulty"],
                "prompt": t["prompt"], "spec": t["spec"],
                "answer": t["answer"], "kind": t["kind"],
            })
    out = config.DATA / f"teacher-batch-{args.seed}.json"
    json.dump(batch, open(out, "w"), indent=1)
    print(f"batch: {len(batch)} tasks -> {out}")
    for t in batch:
        print(f"\n=== {t['task_id']}\n{t['prompt'][:400]}")


def verify(args):
    batch = json.load(open(args.batch))
    out = args.out or str(config.REPLAY)
    ok = fail = 0
    for t in batch:
        trace = t.get("trace")
        if trace is None:
            continue
        spec = t["spec"]
        # verify: the trace's final answer matches the spec, and for tool
        # traces, the tool-call code must actually produce the value
        final = trace[-1]["content"]
        if spec.get("kind") == "expr":
            # the tool call prints the answer; check the stdout
            code = None
            for m in trace:
                if m["role"] == "assistant" and "<tool>" in m["content"]:
                    import re
                    mm = re.search(r'"code":\s*"([^"]+)"', m["content"])
                    if mm:
                        code = mm.group(1).encode().decode("unicode_escape")
                    break
            v = sandbox.run_script(code, expected_stdout=str(spec["expected"])) if code \
                else {"ok": False, "error": "no tool code"}
        elif spec.get("kind") == "tests":
            code = A.extract_code(final) or ""
            v = sandbox.run_code(code, spec)
        elif spec.get("kind") == "script":
            code = A.extract_code(final) or ""
            v = sandbox.run_script(code, files=spec.get("files"),
                                   expected_stdout=spec.get("expected_stdout"))
        else:
            ans = A.extract_answer(final)
            v = {"ok": A.check_text(ans, spec["answer"], spec["how"])}
        if v.get("ok"):
            ok += 1
            with open(out, "a") as f:
                f.write(json.dumps({
                    "task_id": t["task_id"], "family": t["family"],
                    "domain": t["domain"], "difficulty": t["difficulty"],
                    "attempt_kind": "teacher",
                    "messages": trace,
                }, ensure_ascii=False) + "\n")
        else:
            fail += 1
            print(f"FAIL {t['task_id']}: {str(v.get('error'))[:80]}")
    print(f"teacher batch: {ok} verified, {fail} failed -> {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--families", default="arith_chain,bool_expr,closure,math_exec")
    g.add_argument("--n", type=int, default=10)
    g.add_argument("--difficulty", type=int, default=4)
    g.add_argument("--seed", type=int, default=4242)
    v = sub.add_parser("verify")
    v.add_argument("batch")
    v.add_argument("--out", default=None,
                   help="stage verified traces in this JSONL instead of the "
                        "replay buffer (append after the next merge, so the "
                        "traces land inside the next delta window)")
    args = ap.parse_args()
    if args.cmd == "gen":
        gen(args)
    else:
        verify(args)


if __name__ == "__main__":
    main()