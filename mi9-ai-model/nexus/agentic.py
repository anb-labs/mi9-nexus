"""Agentic self-play: ReAct-style tool-use traces for the growth loop.

The current self-play collector asks the model to solve tasks directly. But
the model doesn't know about the `<tool>` protocol — it's never seen it in
training data. This collector generates traces where the model:
  1. receives a task
  2. emits a `<tool>` call (run_python or retrieve)
  3. the sandbox executes it and returns the result
  4. the model sees the result and continues
  5. when done, emits `<answer>...</answer>`

The full trace (including tool calls and results) is stored in the replay
buffer for training. This is the ReAct-style agentic training the whitepaper
describes (Ch. 4.3): the model learns to route to tools, not just answer.

The model doesn't need to be good at tools yet — the STaR hint shows the
reference solution (which includes tool calls), so the model learns from
the verified traces even if its first attempt is poor.
"""
import argparse
import json
import random
import re
import time

from . import config, client, sandbox, tasks, memory
from . import answer as A

TOOL_RE = re.compile(r"<tool>\s*(\{.*?\})\s*</tool>", re.S)
ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.S)
_CODE_RE = re.compile(r'"code"\s*:\s*"(.*)"\s*\}', re.S)
_NAME_RE = re.compile(r'"name"\s*:\s*"(\w+)"')


def parse_tool_call(text):
    """Parse a <tool>...</tool> call. Tolerant of (a) multi-line code that breaks
    strict JSON and (b) truncated calls missing the closing brace before </tool>."""
    text = text or ""
    m = TOOL_RE.search(text)
    if m:
        raw = m.group(1)
        try:
            return json.loads(raw)
        except Exception:
            pass
    # truncated / malformed: salvage the tool name and code directly
    name = _NAME_RE.search(text)
    if not name:
        return None
    cm = re.search(r'<tool>.*?"code"\s*:\s*"(.*?)(?:</tool>|"\s*\})', text, re.S)
    if not cm:
        return None
    code = cm.group(1).rstrip().rstrip('"').rstrip("}").rstrip()
    return {"name": name.group(1), "args": {"code": code}}

AGENT_SYSTEM = (
    "You are a precise reasoning assistant with access to tools. "
    "When you need to compute, emit a tool call as the last thing in your reply:\n"
    "<tool>{\"name\": \"run_python\", \"args\": {\"code\": \"print(2+2)\"}}</tool>\n"
    "When you need to search the local corpus, emit:\n"
    "<tool>{\"name\": \"retrieve\", \"args\": {\"query\": \"...\"}}</tool>\n"
    "When you need up-to-date or world knowledge, search the web:\n"
    "<tool>{\"name\": \"web_search\", \"args\": {\"query\": \"...\"}}</tool>\n"
    "and read a page:\n"
    "<tool>{\"name\": \"web_fetch\", \"args\": {\"url\": \"...\"}}</tool>\n"
    "To read an Office document (docx/pptx/xlsx) by path, emit:\n"
    "<tool>{\"name\": \"office_read\", \"args\": {\"path\": \"...\"}}</tool>\n"
    "After tool results appear, continue reasoning. When you have the final answer, "
    "emit <answer>...</answer>. Use tools for ALL arithmetic — never calculate in your head."
)

HINT_SUFFIX = (
    "\n\nYour previous attempt was wrong. Here is the verified correct solution: "
    "{ans}. Re-solve carefully, using tools for arithmetic, and output in the "
    "exact required format again."
)


def load_json(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def _trim(msgs, max_msgs=10, max_chars=700):
    """Trim the conversation to fit the server context.

    Keeps the system message + the last max_msgs messages, each truncated.
    Multi-turn tool conversations grow fast (tool results are long) and the
    server has a 4096-token context."""
    out = []
    for m in msgs[-max_msgs:]:
        c = m.get("content") or ""
        if len(c) > max_chars:
            c = c[:max_chars] + " ...[truncated]"
        out.append({**m, "content": c})
    if msgs and msgs[0]["role"] == "system" and (not out or out[0]["role"] != "system"):
        sys = msgs[0]
        out = [{**sys, "content": (sys.get("content") or "")[:max_chars]}] + out
    return out


def run_agentic(t, temperature=0.7, max_rounds=6, history=None):
    """Ask the model to solve one task using the tool-use protocol.

    `history` seeds the conversation (used by the STaR retry so the hint
    actually reaches the model). Returns (messages, final_answer, verdict).
    """
    if history is not None:
        msgs = list(history)
    else:
        msgs = [
            {"role": "system", "content": AGENT_SYSTEM},
            {"role": "user", "content": t["prompt"] + " /no_think"},
        ]
    for _ in range(max_rounds):
        raw = client.chat(_trim(msgs), temperature=temperature, max_tokens=1200)
        text = client.strip_thinking(raw["text"])
        if text.startswith("[server error") or text.startswith("[connection error"):
            # server down or restarting — wait briefly and retry this round
            time.sleep(5)
            continue
        m = TOOL_RE.search(text)
        if not m:
            # no tool call — check for final answer
            ans = A.extract_answer(text)
            if ans is not None:
                # the answer must live in the trace: banking stores `msgs`, and
                # without this the trace ends at a tool result — training would
                # then teach the tool call as if it were the final answer
                msgs = msgs + [{"role": "assistant", "content": text}]
                if t["kind"] == "text":
                    ok = A.check_text(ans, t["spec"]["answer"], t["spec"]["how"])
                    return msgs, ans, {"ok": ok, "error": None if ok else "wrong answer"}
                elif t["kind"] == "code":
                    spec = t["spec"]
                    if spec.get("kind") == "expr":
                        # executor already ran (tool result in history); the
                        # final answer must match the ground truth
                        ok = str(ans).strip() == str(spec["expected"]).strip()
                        return msgs, ans, {"ok": ok,
                                           "error": None if ok else "wrong answer"}
                    code = A.extract_code(text)
                    if code:
                        if spec.get("kind") == "expr":
                            verdict = sandbox.run_expr(code, spec["expr"], spec["expected"])
                        elif spec.get("kind") == "script":
                            verdict = sandbox.run_script(code, files=spec.get("files"),
                                                         expected_stdout=spec.get("expected_stdout"))
                        else:
                            verdict = sandbox.run_code(code, spec)
                        return msgs, code, verdict
                    return msgs, code, {"ok": False, "error": "no code block"}
            elif t["kind"] == "code" and A.extract_code(text):
                # code emitted without an <answer> tag (e.g. a truncated file_ops
                # reply): run it and verify rather than looping to max rounds
                code = A.extract_code(text)
                msgs = msgs + [{"role": "assistant", "content": text}]
                spec = t["spec"]
                if spec.get("kind") == "expr":
                    verdict = sandbox.run_expr(code, spec["expr"], spec["expected"])
                elif spec.get("kind") == "script":
                    verdict = sandbox.run_script(code, files=spec.get("files"),
                                                 expected_stdout=spec.get("expected_stdout"))
                else:
                    verdict = sandbox.run_code(code, spec)
                return msgs, code, verdict
            # no answer and no tool call — continue prompting
            continue

        # parse and execute the tool call
        call = parse_tool_call(text)
        if call is None:
            continue

        # execute the tool (one bad call must not kill the cycle)
        try:
            if call.get("name") == "run_python":
                # script tasks (file_ops) need their input files staged in the
                # sandbox; expr/code tasks pass no files
                files = (t.get("spec") or {}).get("files")
                r = sandbox.run_script(call.get("args", {}).get("code", ""), files=files)
                result_text = f"stdout:\n{r.get('stdout', '')}\nerror: {r.get('error', '')}"
            elif call.get("name") == "retrieve":
                hits = memory.query(call.get("args", {}).get("query", ""), k=5)
                result_text = "\n".join(f"[{h['path']}] {h['text'][:300]}" for h in hits)
            elif call.get("name") == "web_search":
                from . import web
                hits = web.search(call.get("args", {}).get("query", ""), limit=5)
                result_text = "\n".join(
                    f"- {h['title']}\n  {h['url']}\n  {h['snippet']}" for h in hits)
            elif call.get("name") == "web_fetch":
                from . import web
                result_text = web.fetch(call.get("args", {}).get("url", ""), max_chars=3000)
            elif call.get("name") == "office_read":
                from . import office
                result_text = office.extract(call.get("args", {}).get("path", ""), max_chars=3000)
            else:
                result_text = f"unknown tool: {call.get('name')}"
        except Exception as e:
            result_text = f"tool error: {type(e).__name__}: {e}"

        # append the tool call and result to the conversation
        msgs = msgs + [
            {"role": "assistant", "content": text},
            {"role": "user", "content":
             f"TOOL RESULT ({call.get('name')}):\n{result_text[:1500]}\n"
             "Continue."},
        ]

    # max rounds reached without final answer
    return msgs, None, {"ok": False, "error": "max rounds"}


def append_jsonl(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def solve_task_once(t, kind_state):
    """One agentic solve cycle with STaR rationalization fallback.

    On failure the reference solution is appended to the conversation as a
    hint and the model retries WITH that history -- the hint must be in the
    prompt for the retry to see it (STaR rationalization, whitepaper Ch. 6).
    """
    t0 = time.time()
    msgs, got, verdict = run_agentic(t)
    kind, kept = "win", verdict.get("ok", False)

    if not kept:
        # STaR rationalization: seed the retry conversation with the hint
        if t["kind"] == "code":
            ans = "this reference solution:\n" + t.get("reference", "")
        else:
            ans = t["spec"].get("answer") or "(see tests)"
        hint = HINT_SUFFIX.format(ans=ans)
        seeded = msgs + [{"role": "user", "content": hint}]
        msgs, got, verdict = run_agentic(t, temperature=0.8, max_rounds=6,
                                         history=seeded)
        kind, kept = "hint", verdict.get("ok", False)

    ep = {
        "task": {k: t[k] for k in ("id", "family", "domain", "difficulty", "kind",
                                   "prompt", "spec")},
        "model_answer": got,
        "correct": bool(kept),
        "attempt_kind": kind,
        "seconds": round(time.time() - t0, 1),
    }
    append_jsonl(config.EPISODES, {**ep, "raw": (msgs[-1].get("content") or "")[:4000]})
    if kept:
        append_jsonl(config.REPLAY, {
            "task_id": t["id"], "family": t["family"], "domain": t["domain"],
            "difficulty": t["difficulty"], "attempt_kind": kind,
            "messages": msgs,
        })

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
        w.append(0.15 + abs(ema - 0.45))
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
                if tasks.generate(f, 1, seed=1) and True]
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
        # AZR-style difficulty control: cap 8 (the generators scale with d;
        # the model mastered d5, the curriculum must find the real edge)
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
              f"| keep-rate {ema:.2f} | W{n_win} H{n_hint} F{n_fail}",
              flush=True)
    json.dump(kind_state, open(config.DATA / "curriculum.json", "w"))
    print(f"done: {i} tasks, {n_win} clean wins, {n_hint} hint wins, {n_fail} fails")


if __name__ == "__main__":
    main()