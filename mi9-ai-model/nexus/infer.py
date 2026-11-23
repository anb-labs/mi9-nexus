"""Test-time compute: repeated sampling + verification.

The 1.7B model is near its weight ceiling; sampling several candidates and
keeping the one the executor verifies recovers much of the gap to a much
larger model (Snell et al. 2024, "Scaling LLM Test-Time Compute"; Brown et al.
2024, "Large Language Monkeys"; Wang et al. 2022, "Self-Consistency").

For code / math / script tasks the sandbox is a ground-truth verifier: we sample
k candidates and return the first that executes correctly. For text tasks we
fall back to majority vote over the extracted answers.
"""
import collections

from . import agentic, answer as A, sandbox
from .selfplay import run_task

# families whose prompts instruct a tool call rather than a ```python fence
TOOL_FAMILIES = {"math_exec", "retrieval_qa"}


def _attempt(t, temperature):
    """One candidate solution attempt; returns (got, verdict)."""
    if t.get("family") in TOOL_FAMILIES:
        _, got, verdict = agentic.run_agentic(t, temperature=temperature, max_rounds=4)
    else:
        _, got, verdict = run_task(t, temperature=temperature)
    return got, verdict


def solve_verified(t, k=5, temperature=0.7):
    """Sample up to k candidates and return the first verified one.

    Returns (answer, verdict, n_tried). If none verify, returns the last
    attempt (so the caller can still see the failure mode).
    """
    got, verdict = None, {"ok": False, "error": "no attempts"}
    for i in range(max(1, k)):
        got, verdict = _attempt(t, temperature)
        if verdict.get("ok"):
            return got, verdict, i + 1
    return got, verdict, max(1, k)


def solve_majority(t, k=5, temperature=0.7):
    """Repeated sampling + majority vote for text tasks (no executor).

    Returns (answer, verdict, votes). Verdict.ok is True iff the majority
    answer passes the task's text check.
    """
    answers = []
    for _ in range(max(1, k)):
        raw, got, _ = run_task(t, temperature=temperature)
        if got is not None:
            answers.append(got)
    if not answers:
        return None, {"ok": False, "error": "no answers"}, 0
    top, n = collections.Counter(answers).most_common(1)[0]
    ok = A.check_text(top, t["spec"]["answer"], t["spec"]["how"]) \
        if t["kind"] == "text" else False
    return top, {"ok": ok, "error": None if ok else "wrong answer"}, n