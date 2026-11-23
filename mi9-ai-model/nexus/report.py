"""Weekly capability report (whitepaper Phase-3 gate): trend across eval reports.

Reads reports/*.json, groups by label prefix (baseline / nightly-before /
nightly-candidate / nightly-after), and prints the capability trajectory on
the frozen and regression suites with per-family movers.
"""
import glob
import json
import os

from . import config


def main():
    rows = []
    for path in sorted(glob.glob(str(config.REPORTS / "*.json"))):
        try:
            r = json.load(open(path))
        except Exception:
            continue
        label = r.get("label", os.path.basename(path))
        suite = "frozen" if "frozen" in r.get("suite", "") else "regression"
        rows.append((label, suite, r["overall_pass1"] * 100, r.get("domains", {})))
    if not rows:
        print("no reports yet")
        return
    print(f"{'when':<22} {'label':<28} {'suite':<11} {'pass@1':>7}")
    for label, suite, pct, _ in rows:
        print(f"{label.split('-')[-1]:<22} {label:<28} {suite:<11} {pct:>6.1f}%")
    print("\nfrozen-suite trajectory (the capability trend):")
    frozen = [r for r in rows if r[1] == "frozen"]
    prev = None
    for label, _, pct, dom in frozen:
        d = f" ({pct - prev:+.1f})" if prev is not None else ""
        doms = "  ".join(f"{k} {v*100:.0f}%" for k, v in dom.items())
        print(f"  {label}: {pct:.1f}%{d}   [{doms}]")
        prev = pct


if __name__ == "__main__":
    main()
