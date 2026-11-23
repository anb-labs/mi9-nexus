"""Serialize the verified replay buffer into llama.cpp finetune training text.

Each verified episode becomes one chat-template block using the exact tokens
the Qwen3 GGUF template produces, so the nightly LoRA trains on precisely what
the runtime will see. Clean wins are repeated twice; hint-assisted wins once
(STaR keeps both, weights differ).
"""
import argparse
import json
import sys

from . import config

TMPL = ("<|im_start|>{role}\n{content}<|im_end|>")


def render_episode(ep):
    parts = []
    for m in ep["messages"]:
        parts.append(TMPL.format(role=m["role"], content=m["content"]))
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-per-family", type=int, default=200)
    args = ap.parse_args()

    eps = []
    seen = set()
    fam_count = {}
    try:
        lines = open(config.REPLAY).read().splitlines()
    except FileNotFoundError:
        print("replay buffer empty - nothing to serialize", file=sys.stderr)
        return
    for line in lines:
        if not line.strip():
            continue
        try:
            ep = json.loads(line)
        except Exception:
            continue
        key = ep.get("task_id") or json.dumps(ep.get("messages", []))[:80]
        if key in seen:
            continue
        seen.add(key)
        if fam_count.get(ep.get("family"), 0) >= args.max_per_family:
            continue
        fam_count[ep.get("family")] = fam_count.get(ep.get("family"), 0) + 1
        eps.append(ep)
    if not eps:
        print("replay buffer empty - nothing to serialize", file=sys.stderr)
        return
    blocks = []
    for ep in eps:
        b = render_episode(ep)
        blocks.append(b)
        if ep.get("attempt_kind") == "win":
            blocks.append(b)  # clean wins carry double weight
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
    out = args.out or (config.DATA / f"train-{stamp}.txt")
    with open(out, "w") as f:
        f.write("\n\n".join(blocks))
    import datetime
    print(f"serialized {len(eps)} episodes ({len(blocks)} blocks, "
          f"{sum(len(b) for b in blocks)} chars) -> {out}")


if __name__ == "__main__":
    main()
