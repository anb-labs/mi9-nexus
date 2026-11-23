"""Growth loop, single step: self-play task -> model solution -> executor verdict.

Implements the whitepaper's nightly loop (Ch. 4.3) with STaR's rationalization
trick (Ch. 6 of the share notes): on a failed attempt the model is shown the
verified answer as a hint and re-solves; if the redo passes, the episode is
kept with kind="hint" so training can weight it lower. Wins are appended to
the replay buffer for the nightly LoRA distillation. Difficulty follows the
keep-rate (AZR's zone-of-proximal-development curriculum).
"""
import argparse
import json
import random
import time

from . import config, client, sandbox, tasks
from . import answer as A

SOLVER_SYSTEM = (
    "You are a precise reasoning assistant. Follow the task's output format "
    "exactly: code tasks want a single ```python block defining the required "
    "function; other tasks want <answer>...</answer>. No extra prose."
)

HINT_SUFFIX = (
    "\n\nYour previous attempt was wrong. Here is the verified correct answer: "
    "{ans}. Re-solve carefully, showing your reasoning, and output in the exact "
    "required format again."
)


def load_json(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def run_task(t, temperature=0.7, think=False):
    """Ask the model to solve one task; returns (raw, extracted, verdict)."""
    sys_msg = SOLVER_SYSTEM if not think else SOLVER_SYSTEM + " Think step by step."
    msgs = [{"role": "system", "content": sys_msg},
            {"role": "user", "content": t["prompt"] + ("" if think else " /no_think")}]
    raw = client.chat(msgs, temperature=temperature, max_tokens=1200)
    text = client.strip_thinking(raw["text"])
    if t["kind"] in ("code", "script"):
        code = A.extract_code(text)
        if code:
            spec = t["spec"]
            if spec.get("kind") == "expr":
                verdict = sandbox.run_expr(code, spec["expr"], spec["expected"])
            elif spec.get("kind") == "script":
                verdict = sandbox.run_script(code, files=spec.get("files"),
                                             expected_stdout=spec.get("expected_stdout"))
            else:
                verdict = sandbox.run_code(code, spec)
        else:
            verdict = {"ok": False, "error": "no code block"}
        return raw, code, verdict
    ans = A.extract_answer(text)
    ok = A.check_text(ans, t["spec"]["answer"], t["spec"]["how"])
    return raw, ans, {"ok": ok, "error": None if ok else "wrong answer"}


def append_jsonl(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def solve_task_once(t, kind_state):
    """One solve cycle with STaR rationalization fallback. Returns episode."""
    t0 = time.time()
    raw, got, verdict = run_task(t, think=False)
    kind, kept = "win", verdict.get("ok", False)
    if not kept:
        # STaR rationalization: show the verified answer, retry
        if t["kind"] == "code":
            ans = "this reference solution:\n" + t.get("reference", "")
        else:
            ans = t["spec"].get("answer") or "(see tests)"
        hint = HINT_SUFFIX.format(ans=ans)
        msgs = [{"role": "system", "content": SOLVER_SYSTEM},
                {"role": "user", "content": t["prompt"] + " /no_think"}]
        raw2 = client.chat(msgs + [{"role": "assistant", "content": client.strip_thinking(raw["text"])},
                                   {"role": "user", "content": hint}],
                           temperature=0.8, max_tokens=1200)
        text2 = client.strip_thinking(raw2["text"])
        if t["kind"] == "code":
            code2 = A.extract_code(text2)
            if code2:
                spec = t["spec"]
                if spec.get("kind") == "expr":
                    verdict = sandbox.run_expr(code2, spec["expr"], spec["expected"])
                elif spec.get("kind") == "script":
                    verdict = sandbox.run_script(code2, files=spec.get("files"),
                                                 expected_stdout=spec.get("expected_stdout"))
                else:
                    verdict = sandbox.run_code(code2, spec)
            else:
                verdict = {"ok": False}
            got, raw = code2, raw2
        else:
            ans2 = A.extract_answer(text2)
            ok2 = A.check_text(ans2, t["spec"]["answer"], t["spec"]["how"])
            verdict, got, raw = {"ok": ok2}, ans2, raw2
        kind, kept = "hint", verdict.get("ok", False)

    if kept and got:
        # a "win" that only echoed the prompt is a verifier false positive:
        # check_text finds the expected answer inside the echoed task text
        if " ".join(str(got).split()) in " ".join(t["prompt"].split()):
            kept = False

    ep = {
        "task": {k: t[k] for k in ("id", "family", "domain", "difficulty", "kind",
                                   "prompt", "spec")},
        "model_answer": got,
        "correct": bool(kept),
        "attempt_kind": kind,
        "seconds": round(time.time() - t0, 1),
    }
    # every attempt is logged (episodic store); only wins enter the replay buffer
    append_jsonl(config.EPISODES, {**ep, "raw": (raw.get("text") or "")[:4000]})
    if kept:
        append_jsonl(config.REPLAY, {
            "task_id": t["id"], "family": t["family"], "domain": t["domain"],
            "difficulty": t["difficulty"], "attempt_kind": kind,
            "messages": [
                {"role": "system", "content": SOLVER_SYSTEM},
                {"role": "user", "content": t["prompt"] + " /no_think"},
                {"role": "assistant",
                 "content": client.strip_thinking(raw.get("text") or "").strip()},
            ],
        })
    # curriculum: keep-rate EMA per family
    prev = kind_state.get(t["family"], {"ema": 0.5, "n": 0})
    alpha = 0.25
    prev["ema"] = (1 - alpha) * prev["ema"] + alpha * (1.0 if kept else 0.0)
    prev["n"] += 1
    kind_state[t["family"]] = prev
    return ep


def pick_family(kind_state, families):
    """Weight families toward keep-rates near the learnable band."""
    w = []
    for f in families:
        ema = kind_state.get(f, {}).get("ema", 0.5)
        w.append(0.15 + abs(ema - 0.45))  # closer to band -> higher weight
    return random.choices(families, weights=w, k=1)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=config.SELFPLAY_TIME_BUDGET_MIN)
    ap.add_argument("--max-tasks", type=int, default=100000)
    ap.add_argument("--domains", default="code,math,logic")
    args = ap.parse_args()

    if not client.health():
        raise SystemExit("llama-server is not up (nexus serve start)")
    domains = set(args.domains.split(","))
    families = [f for f in tasks.FAMILIES
                if tasks.generate(f, 1, seed=1) and True]  # all generate fine
    fam_domain = {}
    for f in families:
        t = tasks.generate(f, 1, seed=3)
        fam_domain[f] = t["domain"]
    use = [f for f in families if fam_domain[f] in domains]
    kind_state = load_json(config.DATA / "curriculum.json", {})
    n_win = n_hint = n_fail = 0
    t_end = time.time() + args.minutes * 60
    i = 0
    while time.time() < t_end and i < args.max_tasks:
        f = pick_family(kind_state, use)
        d = kind_state.get(f, {}).get("d", 2)
        t = tasks.generate(f, d)
        if t is None:
            continue
        i += 1
        ep = solve_task_once(t, kind_state)
        n_win += ep["correct"] and ep["attempt_kind"] == "win"
        n_hint += ep["correct"] and ep["attempt_kind"] == "hint"
        n_fail += not ep["correct"]
        ema = kind_state[f]["ema"]
        # AZR-style difficulty control inside the learnable band.
        # Cap at 8 (was 5): the generators scale with d, and the model has
        # mastered d5 -- the curriculum must find the real edge of ability.
        if ema > config.DIFFICULTY_UP:
            d2 = min(8, d + 1)
        elif ema < config.DIFFICULTY_DOWN:
            d2 = max(1, d - 1)
        else:
            d2 = d
        kind_state[f]["d"] = d2
        if i % 5 == 0 or time.time() > t_end:
            json.dump(kind_state, open(config.DATA / "curriculum.json", "w"))
        print(f"[{i:4d}] {f:18s} d{d} {ep['attempt_kind']:5s} "
              f"{'PASS' if ep['correct'] else 'FAIL'} {ep['seconds']:5.1f}s "
              f"| keep-rate {ema:.2f} | W{ n_win} H{n_hint} F{n_fail}",
              flush=True)
    json.dump(kind_state, open(config.DATA / "curriculum.json", "w"))
    print(f"done: {i} tasks, {n_win} clean wins, {n_hint} hint wins, {n_fail} fails")


if __name__ == "__main__":
    main()
