#!/usr/bin/env python3
"""Clean the replay buffer and keep the delta marker meaningful.

A trace is kept only if it ends with an assistant answer in serving format.
The merge marker is a LINE COUNT, so deleting lines would silently shift the
delta window; the marker is recomputed as "kept lines among the first N".

Usage:
  python3 tools/replay_clean.py            # dry run, report only
  python3 tools/replay_clean.py --apply    # rewrite buffer + marker
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nexus import config  # noqa: E402
from nexus.train import _episode_ok  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    lines = config.REPLAY.read_text().splitlines()
    marker = int((config.DATA / "last-merge.txt").read_text().strip() or 0)

    kept, dropped, flags = [], [], []
    for i, line in enumerate(lines):
        try:
            ep = json.loads(line)
        except Exception:
            flags.append(False)
            dropped.append((i, "unparseable", "?"))
            continue
        if _episode_ok(ep):
            flags.append(True)
            kept.append(line)
        else:
            flags.append(False)
            last = (ep.get("messages") or [{}])[-1]
            reason = (f"last msg is {last.get('role')}"
                      if last.get("role") != "assistant"
                      else "no serving-format answer")
            dropped.append((i, reason, ep.get("attempt_kind")))

    new_marker = sum(1 for i, ok in enumerate(flags) if ok and i < marker)
    # The marker is a line offset, so dropping pre-boundary lines legitimately
    # moves it down -- the recompute keeps the delta window pointing at the same
    # logical (not-yet-trained) episodes. Never let it exceed the kept line count.
    if new_marker > len(kept):
        print(f"WARNING: recomputed marker {new_marker} exceeds kept lines "
              f"{len(kept)}; clamping", file=sys.stderr)
        new_marker = len(kept)
    if new_marker != marker:
        print(f"note: marker {marker} -> {new_marker} (line-offset recompute after "
              f"dropping {marker - new_marker} pre-boundary line(s); delta window "
              f"still starts at the same logical episode)")

    print(f"buffer: {len(lines)} lines, marker {marker}")
    print(f"keep:   {len(kept)}  drop: {len(dropped)}")
    print("dropped by kind:  ", dict(collections.Counter(d[2] for d in dropped)))
    print("dropped by reason:", dict(collections.Counter(d[1] for d in dropped)))
    print(f"new marker: {new_marker}  "
          f"(delta window keeps {len(kept) - new_marker} episodes)")

    if args.apply:
        config.REPLAY.write_text("\n".join(kept) + "\n")
        (config.DATA / "last-merge.txt").write_text(str(new_marker))
        print("applied.")
    else:
        print("dry run - pass --apply to rewrite")


if __name__ == "__main__":
    main()
