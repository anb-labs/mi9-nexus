#!/usr/bin/env python3
"""Measure output-format distribution across domains, not just pass/fail.

smoke.py answers "is the served model sane?" with one task per domain. That is
too coarse to separate *format drift* from *hard task*, and the champion itself
fails some hard picks. This probe samples N tasks per domain and reports, per
domain, how many replies had a ```python fence / <answer> tag / neither, plus
how many were actually correct. Use it to decide whether a delta caused format
leakage (e.g. math answered with a code fence) before running a full eval.

Usage:
  python3 tools/format_probe.py                  # 6 tasks per domain
  python3 tools/format_probe.py --per-domain 10
  NEXUS_UPSTREAM=http://host:port python3 tools/format_probe.py
"""
import argparse
import json
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nexus import answer as A, sandbox  # noqa: E402

UPSTREAM = "http://127.0.0.1:8080"
SYSTEM = ("You are a precise reasoning assistant. Follow the task's output "
          "format exactly: code tasks want a single ```python block defining "
          "the required function; other tasks want <answer>...</answer>. No "
          "extra prose.")
FENCE = re.compile(r"```")


def ask(prompt, max_tokens=300):
    body = json.dumps({
        "model": "nexus/micro",
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.0, "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(f"{UPSTREAM}/v1/chat/completions", body,
                                 {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-domain", type=int, default=6)
    ap.add_argument("--materialize-check", action="store_true",
                    help="actually execute code / compare answers (slower)")
    args = ap.parse_args()

    suite = json.load(open(ROOT / "suites" / "regression.json"))
    rows = []
    for domain in ("code", "math", "logic"):
        picks = [t for t in suite if t["domain"] == domain][: args.per_domain]
        for t in picks:
            reply = ask(t["prompt"])
            code = A.extract_code(reply)
            if t["kind"] == "code":
                fmt = "fence" if code else ("answer-wrap" if "<answer>" in reply else "none")
                ok = False
                err = ""
                if code and args.materialize_check:
                    v = sandbox.run_code(code, t["spec"])
                    ok = bool(v.get("ok"))
                    err = (v.get("error") or "")[:50]
                elif code:
                    ok = True
            else:
                ans = A.extract_answer(reply)
                fmt = "answer" if ans is not None else ("fence" if FENCE.search(reply) else "none")
                ok = None
                err = ""
                if ans is not None and args.materialize_check:
                    try:
                        ok = A.check_text(ans, t["spec"]["answer"], t["spec"]["how"])
                    except Exception as e:  # noqa: BLE001
                        ok = False
                        err = type(e).__name__
                elif ans is not None:
                    ok = True
            rows.append((domain, t["id"], fmt, ok, err))
            flag = "" if fmt in ("fence", "answer") else "  <-- FORMAT MISS"
            print(f"{domain:5s} {t['id']:32s} fmt={fmt:12s} ok={ok}{flag} {err}")

    print()
    for domain in ("code", "math", "logic"):
        c = Counter(r[2] for r in rows if r[0] == domain)
        print(f"{domain:5s} formats: {dict(c)}")
    misses = [r for r in rows if r[2] == "none"]
    print(f"\nformat misses: {len(misses)}/{len(rows)}")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
