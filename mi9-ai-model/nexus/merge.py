"""Merge-and-carry: bake the champion LoRA into the base model.

Whitepaper Ch. 4.3 (cumulative growth): each nightly trains a *delta* on top
of the accumulated model, not a fresh LoRA from the stock base. Training a
new LoRA from the stock base every cycle re-learns everything and drifts --
cycle 2 regressed code/logic exactly this way (gate rollback, 2026-11-13).

Flow per promotion:
  1. champion peft adapter + current base -> merge_and_unload() -> new base
     (safetensors, cached under models/merged-<champion-ts>/)
  2. next training run loads that merged dir as its base
  3. serving uses merged GGUF + the new delta adapter

Rollback stays trivial: the previous merged dir / GGUF is never overwritten.
"""
import argparse
from pathlib import Path

from . import config


def merged_dir_for(champion_peft: Path) -> Path:
    """Cache dir for the merge of a given champion adapter."""
    ts = champion_peft.name.replace("peft-", "")
    return config.MODELS / f"merged-{ts}"


def merge_champion(champion_peft: Path, out_dir: Path = None) -> Path:
    """merge_and_unload the champion adapter into the current base.

    Base resolution: the newest existing merged-* dir (the accumulated
    model), else the official snapshot. Returns the merged dir.
    """
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    existing = sorted(config.MODELS.glob("merged-*"))
    base = existing[-1] if existing else config.HF_SNAPSHOT
    out_dir = out_dir or merged_dir_for(champion_peft)
    if out_dir.exists():
        print(f"merge cache hit: {out_dir}")
        return out_dir

    print(f"merging champion {champion_peft.name} into base {base.name} ...")
    model = AutoModelForCausalLM.from_pretrained(str(base), dtype=torch.bfloat16)
    model = PeftModel.from_pretrained(model, str(champion_peft))
    model = model.merge_and_unload()
    model.save_pretrained(str(out_dir))
    # tokenizer comes from the snapshot (the peft dir has one too, but the
    # snapshot's chat template is the source of truth)
    for f in ("tokenizer_config.json", "tokenizer.json", "vocab.json",
              "merges.txt", "generation_config.json"):
        src = config.HF_SNAPSHOT / f
        if src.exists() and not (out_dir / f).exists():
            (out_dir / f).write_bytes(src.read_bytes())
    print(f"merged model saved -> {out_dir}")
    # mark the replay position so the next training run only sees new episodes
    # (the merged base already contains everything up to here)
    try:
        n = sum(1 for _ in open(config.REPLAY))
        (config.DATA / "last-merge.txt").write_text(str(n))
    except Exception:
        pass
    return out_dir


def current_base() -> Path:
    """The training base: newest merge if one exists, else the snapshot."""
    existing = sorted(config.MODELS.glob("merged-*"))
    return existing[-1] if existing else config.HF_SNAPSHOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--champion", required=True, help="peft adapter dir to bake in")
    args = ap.parse_args()
    d = merge_champion(Path(args.champion))
    print(d)


if __name__ == "__main__":
    main()