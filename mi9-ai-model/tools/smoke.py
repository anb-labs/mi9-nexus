#!/usr/bin/env python3
"""60-second format smoke test for a served model.

Runs one task of each output format through the real server and checks the
answer the way eval does. Catches the failures that cost whole cycles:
  - code wrapped in <answer> instead of a ```python block (format drift)
  - a broken LoRA conversion producing degenerate output ("DONE")
  - text answers missing <answer>

Usage:
  python3 tools/smoke.py                 # 3 tasks: code, math, logic
  NEXUS_UPSTREAM=http://host:port python3 tools/smoke.py
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nexus import answer as A, sandbox  # noqa: E402

UPSTREAM = "http://127.0.0.1:8080"
SYSTEM = ("You are a precise reasoning assistant. Follow the task's output "
          "format exactly: code tasks want a single ```python block defining "
          "the required function; other tasks want <answer>...</answer>. No "
          "extra prose.")


def ask(prompt, max_tokens=400):
    body = json.dumps({
        "model": "nexus/micro",
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.0, "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(f"{UPSTREAM}/v1/chat/completions", body,
                                 {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def check_code(t):
    reply = ask(t["prompt"])
    code = A.extract_code(reply)
    if not code:
        return False, f"no ```python block; got {reply[:80]!r}"
    v = sandbox.run_code(code, t["spec"])
    return bool(v.get("ok")), (v.get("error") or "tests pass")[:70]


def check_text(t):
    reply = ask(t["prompt"], max_tokens=250)
    ans = A.extract_answer(reply)
    if ans is None:
        return False, f"no <answer>; got {reply[:80]!r}"
    ok = A.check_text(ans, t["spec"]["answer"], t["spec"]["how"])
    return ok, f"answer={ans!r}"


def main():
    suite = json.load(open(ROOT / "suites" / "regression.json"))
    picks = [next(t for t in suite if t["domain"] == d) for d in ("code", "math", "logic")]
    failed = 0
    for t in picks:
        try:
            ok, detail = (check_code if t["kind"] == "code" else check_text)(t)
        except Exception as e:
            ok, detail = False, f"error: {type(e).__name__}: {e}"
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {t['id']:34s} {detail}")
    print(f"\n{len(picks) - failed}/{len(picks)} formats OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
