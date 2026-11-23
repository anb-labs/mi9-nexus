"""Continued pre-training (CPT) on a code corpus (whitepaper Ch. 4.3, the
"raw data -> weights" lever; cf. DiffLM ACL 2025, SBP ICLR 2026).

The model's ceiling is its 1.7B of pretrained knowledge. Self-play data is
narrow (task families); CPT on a broad code corpus shifts the distribution
toward real-world code. Method: LoRA-based CPT of the merged base at a LOW
learning rate (1e-5) -- the base is frozen, only the adapter learns, so the
update is small, gated, and rollback-able.

Data: corpus/code/*.py (default: the Python 3.12 stdlib, ~46 MB). Sequences
are raw token chunks (causal LM objective, no chat template -- this is
pretraining-style exposure, not instruction tuning).

Memory: same budget as train.py (~4.5 GB peak with the fp32-GEMM patch).
The llama-server must be stopped while training.
"""
import argparse
import datetime
import glob
import math
import random
import sys

from . import config


def load_code_chunks(ctx=512, max_seqs=500, seed=7):
    """Tokenize the code corpus into fixed-size chunks (subsampled)."""
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(config.HF_SNAPSHOT))
    files = sorted(glob.glob(str(config.CORPUS / "code" / "*.py")))
    if not files:
        files = sorted(glob.glob(str(config.CORPUS / "*.py")))
    if not files:
        print("no code corpus found (corpus/code/*.py)", file=sys.stderr)
        return None, []
    rng = random.Random(seed)
    rng.shuffle(files)
    seqs = []
    for fp in files:
        if len(seqs) >= max_seqs:
            break
        try:
            text = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        ids = tok(text, add_special_tokens=False)["input_ids"]
        # chunk into ctx-sized windows
        for i in range(0, len(ids) - ctx, ctx):
            if len(seqs) >= max_seqs:
                break
            seqs.append(ids[i:i + ctx])
    return tok, seqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--ctx", type=int, default=512)
    ap.add_argument("--max-seqs", type=int, default=500)
    ap.add_argument("--kl-max", type=float, default=0.0,
                    help="optional KL-to-base leash (liminal CPT)")
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM

    from .train import install_chunked_cross_entropy, install_fp32_gemm_fallback

    install_fp32_gemm_fallback()
    install_chunked_cross_entropy()
    tok, seqs = load_code_chunks(ctx=args.ctx, max_seqs=args.max_seqs)
    if not seqs:
        return
    print(f"CPT corpus: {len(seqs)} sequences x {args.ctx} tokens "
          f"({len(seqs) * args.ctx // 1000}k tokens)")

    model = AutoModelForCausalLM.from_pretrained(
        str(config.HF_SNAPSHOT), dtype=torch.bfloat16)
    model.config.use_cache = False
    # checkpointing ON: measured 42 s/step at 4.3 GB RSS (stays in RAM) vs
    # 84 s/step at 6.0 GB without (swap-thrashing on this 8 GB box)
    model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)

    from peft import LoraConfig, get_peft_model
    lcfg = LoraConfig(
        r=config.LORA_R, lora_alpha=config.LORA_ALPHA, lora_dropout=0.05,
        bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(model, lcfg)
    model.print_trainable_parameters()
    for p in model.parameters():
        if p.requires_grad:
            p.data = p.data.float()
    model.train()

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=args.lr, weight_decay=0.0)
    total = args.epochs * len(seqs)
    step, warm = 0, max(5, total // 20)
    rng = random.Random(7)
    t0 = datetime.datetime.now()
    losses = []
    for epoch in range(args.epochs):
        order = list(range(len(seqs)))
        rng.shuffle(order)
        for i in order:
            x = torch.tensor([seqs[i]])
            y = x.clone()
            lr_scale = step / warm if step < warm else \
                0.5 * (1 + math.cos(math.pi * step / max(1, total - warm)))
            for g in opt.param_groups:
                g["lr"] = args.lr * max(0.05, lr_scale)
            kl_w = args.kl_max * max(0.0, 1.0 - step / max(1, total * 0.7))
            if kl_w > 0:
                with torch.no_grad():
                    with model.disable_adapter():
                        base_logits = model(input_ids=x).logits
            out = model(input_ids=x, labels=y)
            if kl_w > 0:
                import torch.nn.functional as F
                kl = F.kl_div(
                    F.log_softmax(out.logits[:, :-1].float().reshape(-1, out.logits.shape[-1]), dim=-1),
                    F.log_softmax(base_logits[:, :-1].float().reshape(-1, base_logits.shape[-1]), dim=-1),
                    reduction="batchmean", log_target=True,
                )
                loss = out.loss + kl_w * kl
            else:
                loss = out.loss
            (loss / 4).backward()
            if (step + 1) % 4 == 0:
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], 1.0)
                opt.step()
                opt.zero_grad()
            losses.append(out.loss.item())
            step += 1
            if step % 10 == 0:
                el = (datetime.datetime.now() - t0).total_seconds()
                rss = int(open("/proc/self/status").read()
                          .split("VmRSS:")[1].split()[0]) // 1024
                print(f"step {step}/{total} loss {sum(losses[-20:])/len(losses[-20:]):.3f} "
                      f"rss {rss}MB ({el/step:.1f}s/step)", flush=True)

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = str(config.ADAPTERS / f"cpt-{ts}")
    model.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)
    print(f"saved CPT adapter -> {out_dir}")
    print(f"final loss {sum(losses[-20:])/len(losses[-20:]):.3f}")


if __name__ == "__main__":
    main()