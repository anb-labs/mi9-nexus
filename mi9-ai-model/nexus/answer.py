"""Answer extraction and normalization for the verifier stack.

Protocol: the model must wrap its final answer in <answer>...</answer> and/or
emit exactly one ```python code block for code tasks. Anything else is scored
as invalid - the executor, not the model, decides correctness.
"""
import re
from fractions import Fraction

ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.S | re.I)
CODE_RE = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.S)


def extract_code(text):
    blocks = CODE_RE.findall(text or "")
    return blocks[-1].strip() if blocks else None


def extract_answer(text):
    m = ANSWER_RE.findall(text or "")
    if m:
        return m[-1].strip()
    return None


def norm(value, how):
    """Normalize a text answer according to the family's canonical form."""
    s = (value or "").strip().strip("`'\" ")
    try:
        if how == "int":
            return int(s.replace(",", "").replace(" ", ""))
        if how == "num":
            return float(s.replace(",", "").replace(" ", ""))
        if how == "frac":
            return Fraction(s.replace(" ", ""))
        if how == "tuple_int":
            return tuple(int(x) for x in re.findall(r"-?\d+", s))
        if how == "lower":
            return s.lower()
        if how == "tokens":
            return tuple(s.lower().replace(" ", "").split(","))
    except Exception:
        pass
    return s


def check_text(predicted, expected, how):
    if predicted is None:
        return False
    try:
        if how == "contains":
            # keyword-substring check for free-form answers (retrieval-qa):
            # every comma-separated expected term must appear in the answer
            return all(t.strip().lower() in predicted.lower()
                       for t in str(expected).split(",") if t.strip())
        return norm(predicted, how) == norm(expected, how)
    except Exception:
        return False
