"""Schema extraction: turn verified traces into reusable playbooks.

Whitepaper Ch. 4.3 / human-learning mapping (Chase & Simon "chunks"): humans
don't remember individual tasks -- they remember *patterns*. This module does
the same for the model:

  1. read every verified replay episode
  2. cluster by (family, solution-shape) -- the shape is the structure of the
     answer (which primitives it uses, how it's composed), not the data
  3. write one playbook per cluster into the memory index (FTS5 + BM25)
  4. at inference, retrieval surfaces the right playbook for the current task

The playbook is *strategy*, not data: it teaches "gcd -> factor both numbers",
which generalizes to any gcd task, instead of storing 100 specific answers.

Playbooks are versioned by family so a new distillation cycle can refresh them
without touching the corpus.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import config, memory, tasks


def _answer_text(ep):
    msgs = ep.get("messages") or []
    return (msgs[-1].get("content") or "") if msgs else ""


def solution_shape(ep, family):
    """A coarse structural signature of a solution, independent of the data.

    For code: which stdlib primitives appear (math, itertools, collections),
    whether it uses recursion, list comprehensions, etc.
    For text: the answer's type (int/str/bool/list) and length band.
    """
    answer = _answer_text(ep)
    if family in tasks.CODE_FAMILIES:
        text = answer or ""
        feats = []
        for kw in ("import math", "import itertools", "import collections",
                   "from math", "def ", "return", "for ", "while ",
                   "recursion", "lambda", "sorted(", "set(", "dict(",
                   "bin(", "chr(", "ord(", "reverse", "join", "split"):
            if kw in text:
                feats.append(kw)
        return "+".join(sorted(feats)) or "plain"
    # text answers: type + length band
    a = str(answer)
    kind = "int" if a.lstrip("-").isdigit() else \
           "bool" if a.lower() in ("true", "false", "yes", "no") else \
           "list" if a.startswith(("[", "(")) else "word"
    band = "short" if len(a) <= 4 else "med" if len(a) <= 12 else "long"
    return f"{kind}:{band}"


def build_playbooks(replay_path=None, out_dir=None):
    """Cluster verified traces and write playbooks to the memory index."""
    replay_path = replay_path or config.REPLAY
    out_dir = out_dir or config.CORPUS / "playbooks"
    out_dir.mkdir(parents=True, exist_ok=True)

    eps = []
    for line in open(replay_path):
        try:
            eps.append(json.loads(line))
        except Exception:
            continue
    if not eps:
        print("no replay episodes to extract schemas from", file=sys.stderr)
        return 0

    # group by (family, shape)
    groups = defaultdict(list)
    for ep in eps:
        fam = ep.get("family", "?")
        shape = solution_shape(ep, fam)
        groups[(fam, shape)].append(ep)

    written = 0
    for (fam, shape), members in sorted(groups.items()):
        # the playbook: one representative trace per family/shape, annotated
        # with what made it succeed and the general strategy
        m = members[0]
        msgs = m["messages"]
        prompt = msgs[1]["content"] if len(msgs) > 1 else ""
        answer = (msgs[-1].get("content") or "").strip()[:600]
        doc = (
            f"PLAYBOOK [{fam}] shape={shape} "
            f"(n={len(members)} verified traces)\n"
            f"Strategy: solve any {fam} task of this shape the same way.\n"
            f"Example prompt: {prompt[:300]}\n"
            f"Example answer: {answer}\n"
        )
        # write to disk + index
        slug = f"{fam}__{re.sub(r'[^a-z0-9]+','_',shape)}.md"
        (out_dir / slug).write_text(doc, encoding="utf-8")
        written += 1

    # index the playbook directory into the FTS5 store
    memory.index(out_dir)
    print(f"extracted {written} playbooks from {len(eps)} traces -> {out_dir}")
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    build_playbooks(args.replay, args.out)


if __name__ == "__main__":
    main()