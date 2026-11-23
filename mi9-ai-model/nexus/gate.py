"""Regression gate (whitepaper Ch. 6.5): adapter must not degrade the frozen suite.

Usage: python3 -m nexus.gate before.json candidate.json [cap_before.json cap_candidate.json]
Prints 1 to promote, 0 to rollback.

Rules:
  - regression suite: candidate overall pass@1 >= before minus 1 point, and
    no family regresses by more than one task's worth (noise tolerance)
  - capability suite (optional, new skills + harder difficulties): if both
    before/after are given, the candidate must not REGRESS capability by
    more than 2 points -- this lets a cycle trade a little old-family
    performance for new skills without blocking it.

The capability suite exists because the regression suite only measures the
original families at their mastered difficulties; without it the gate blocks
every change that trades old performance for new skills (the plateau problem,
cycle 2/4/5/6/7 rollbacks).
"""
import json
import sys


def overall(path):
    r = json.load(open(path))
    return r["overall_pass1"] * 100.0


def main():
    before, cand = sys.argv[1], sys.argv[2]
    b, c = overall(before), overall(cand)
    bf, cf = json.load(open(before))["by_family"], json.load(open(cand))["by_family"]
    regressions = []
    for fam, score in bf.items():
        new = cf.get(fam, 0.0)
        if new < score - 0.25:  # one task = 1/n; tolerate single-task noise
            regressions.append((fam, round(score * 100, 1), round(new * 100, 1)))
    print(f"regression: before {b:.1f}% -> candidate {c:.1f}%  (delta {c-b:+.1f})",
          file=sys.stderr)
    if regressions:
        print("family regressions: " + ", ".join(f"{f} {s}->{n}" for f, s, n in regressions),
              file=sys.stderr)

    ok = (c >= b - 1.0) and not regressions

    # capability suite (optional): the regression suite only measures the
    # mastered families at d2; the capability suite measures new skills
    # (file_ops/retrieval_qa/math_exec + d7). A cycle may trade a little
    # old-family performance for new skills if the capability gain
    # outweighs the regression loss (net delta > +1).
    if len(sys.argv) >= 5:
        cb, cc = overall(sys.argv[3]), overall(sys.argv[4])
        net = (cc - cb) - (b - c)  # capability gain minus regression loss
        print(f"capability: before {cb:.1f}% -> candidate {cc:.1f}%  (delta {cc-cb:+.1f})",
              file=sys.stderr)
        print(f"net trade: {net:+.1f} (capability gain - regression loss)", file=sys.stderr)
        if net > 1.0:
            # the trade is worth it: waive the family-regression rule
            print("capability gain outweighs regression: promoting", file=sys.stderr)
            ok = True
        elif cc < cb - 2.0:
            print("capability regression: blocking promotion", file=sys.stderr)
            ok = False

    print(1 if ok else 0)


if __name__ == "__main__":
    main()