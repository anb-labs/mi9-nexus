"""Nightly LoRA distiller (whitepaper Ch. 4.3 / Phase 3, scaled to CPU).

Trains a LoRA adapter (r=16) on the verified replay buffer with PyTorch+PEFT
on CPU. The frozen base is the Q8_0 GGUF read directly by transformers'
GGUF integration (dequantized to bf16, ~3.4 GB RAM). Sequence goal: fold the
day's verified wins into a swappable adapter, megabytes, rollback-able.

Steps:
  1. load base (Q8_0 gguf -> bf16) + tokenizer from the same file
  2. render each replay episode with the model's own chat template
  3. LoRA finetune (AdamW, cosine decay, grad accumulation)
  4. save peft adapter to adapters/peft-<ts>/
  5. convert to GGUF for llama-server --lora  (convert_lora_to_gguf.py)

Memory budget: ~4 GB. The llama-server must be stopped while training.
"""
import argparse
import datetime
import json
import math
import os
import random
import re
import sys
from pathlib import Path

from . import config, sandbox
from .merge import current_base

RENDER = ("<|im_start|>{role}\n{content}<|im_end|>\n")
TOOL_CALL_RE = re.compile(r"<tool>\s*(\{.*?\})\s*</tool>", re.S)


def _episode_ok(ep):
    """A trainable trace must END with an assistant answer in serving format.

    Collector bugs can bank traces that stop at a tool result (the answer was
    verified but never appended) or that only echo the prompt. Training on
    those teaches the tool call as the answer, so reject them here — defense in
    depth behind the collectors' own checks.
    """
    msgs = ep.get("messages") or []
    if not msgs or msgs[-1].get("role") != "assistant":
        return False
    final = (msgs[-1].get("content") or "").strip()
    if not final or "Traceback (most recent call last)" in final:
        return False
    return "<answer>" in final or "```" in final


def _tool_calls_ok(msgs):
    """Replay every tool call in a trace; return False if any fails.

    Self-play can emit junk calls (out-of-range indexes, empty queries). A
    trace whose tool call errors is not safe tool-turn training data: the
    model would learn to call tools wrongly.
    """
    for m in msgs:
        if m["role"] != "assistant":
            continue
        for raw in TOOL_CALL_RE.findall(m.get("content") or ""):
            try:
                call = json.loads(raw)
            except Exception:
                return False
            name = call.get("name")
            args = call.get("args") or {}
            if name == "run_python":
                code = str(args.get("code") or "")
                if not code.strip() or not sandbox.run_script(code).get("ok"):
                    return False
            elif name == "retrieve":
                if not str(args.get("query") or "").strip():
                    return False
            else:
                return False
    return True


def install_chunked_cross_entropy():
    """CE in 256-token vocab chunks. The 1.7B fp32 logits tensor is 311 MB and
    F.cross_entropy's internal copies double it -- that spike OOM-killed the
    run on this 8 GB box. Chunking over the token dim keeps the math identical
    (mean over all tokens) with a transient of a few MB."""
    import torch
    import torch.nn.functional as F

    orig_ce = F.cross_entropy

    def ce(input, target, weight=None, ignore_index=-100, reduction="mean", **kw):
        if (reduction != "mean" or weight is not None
                or input.dtype != torch.float32 or input.dim() < 2):
            return orig_ce(input, target, weight=weight,
                           ignore_index=ignore_index, reduction=reduction, **kw)
        flat_t = target.reshape(-1)
        n = flat_t.numel()
        total = input.new_zeros(())
        for c0 in range(0, n, 256):
            c1 = min(n, c0 + 256)
            total = total + orig_ce(input.reshape(n, -1)[c0:c1], flat_t[c0:c1],
                                    ignore_index=ignore_index,
                                    reduction="sum", **kw)
        return total / max(1, n - (flat_t == ignore_index).sum())

    F.cross_entropy = ce


def install_fp32_gemm_fallback():
    """torch 2.15's half-precision CPU GEMM is broken on AVX2-only CPUs
    (measured 0.3 GFLOP/s vs 148.6 for fp32). Route every bf16 nn.Linear
    through fp32 math with a custom autograd Function that saves only the
    bf16 originals for backward, so no large fp32 copies are retained."""
    import torch
    import torch.nn as nn

    class UpcastLinear(torch.autograd.Function):
        @staticmethod
        def forward(ctx, x, w, b):
            ctx.save_for_backward(x, w, b)
            y = x.float() @ w.float().T
            if b is not None:
                y = y + b.float()
            return y

        @staticmethod
        def backward(ctx, dy):
            x, w, b = ctx.saved_tensors
            dx = dw = db = None
            dy2 = dy.reshape(-1, dy.shape[-1])
            if ctx.needs_input_grad[0]:
                wf = w.float()
                dx = (dy @ wf).to(x.dtype)
            if ctx.needs_input_grad[1]:
                dw = (dy2.T @ x.reshape(-1, x.shape[-1]).float()).to(w.dtype)
            if b is not None and ctx.needs_input_grad[2]:
                db = dy2.sum(0).to(b.dtype)
            return dx, dw, db

    orig = nn.Linear.forward

    def fp32_linear(self, x):
        if self.weight.dtype == torch.bfloat16:
            return UpcastLinear.apply(x, self.weight, self.bias)
        return orig(self, x)

    nn.Linear.forward = fp32_linear


def load_replay(max_per_family=200, since_line=0):
    """Load verified episodes, optionally only those appended after a given
    line count (delta-training: the merged base already contains the old
    episodes' knowledge; re-training on them causes drift/forgetting)."""
    eps, seen, fam = [], set(), {}
    skipped = 0
    for i, line in enumerate(open(config.REPLAY)):
        if i < since_line:
            continue
        try:
            ep = json.loads(line)
        except Exception:
            continue
        key = ep.get("task_id")
        if key in seen:
            continue
        seen.add(key)
        if not _episode_ok(ep):
            skipped += 1
            continue
        if fam.get(ep.get("family"), 0) >= max_per_family:
            continue
        fam[ep.get("family")] = fam.get(ep.get("family"), 0) + 1
        eps.append(ep)
    return eps, skipped


def _skill_of(ep):
    """Classify a trace by the skill it teaches: 'code' if the final assistant
    answer contains a ```python block, else 'answer' (bare <answer>...</answer>).

    A single-skill batch (e.g. an all-math delta) teaches the model to emit only
    <answer>...</answer> and forgets how to write code -- the collapse seen in
    train-15 (code 95% -> 0%).
    """
    msgs = ep.get("messages") or []
    if not msgs:
        return "answer"
    c = str(msgs[-1].get("content") or "")
    return "code" if "```" in c else "answer"


def balance_eps(eps, full_eps, min_ratio=0.3, cap=40):
    """Ensure both skills (code + answer) are represented in the training set.

    If a skill is entirely absent from the delta, backfill the most recent
    examples of it from the full buffer (deduped) so the model does not forget
    that skill. The backfill brings the missing skill up to ~`min_ratio` of the
    present skill's count (capped at `cap`) -- enough to retain the skill without
    re-training heavily on already-merged episodes. Returns (eps, n_backfilled).
    """
    present = {}
    for e in eps:
        s = _skill_of(e)
        present[s] = present.get(s, 0) + 1
    missing = [s for s in ("code", "answer") if present.get(s, 0) == 0]
    if not missing:
        return eps, 0
    maj = max(present.values())
    target = min(int(maj * min_ratio), cap)
    seen = {e.get("task_id") for e in eps}
    added = []
    for e in reversed(full_eps):          # most recent first
        if len(added) >= target:
            break
        if e.get("task_id") in seen:
            continue
        s = _skill_of(e)
        if s in missing:
            added.append(e)
            seen.add(e.get("task_id"))
    return eps + added, len(added)


def rehearse(eps, full_eps, n):
    """Sample up to n pre-merge episodes (not in the delta) to mix into training.

    Rehearsal/replay is the standard anti-catastrophic-forgetting technique
    (2508.06178, 2501.13669): replaying already-learned examples while learning new
    ones keeps the model from overwriting prior skills. Returns the sampled list.
    """
    seen = {e.get("task_id") for e in eps}
    pool = [e for e in full_eps if e.get("task_id") not in seen]
    rng = random.Random(11)
    rng.shuffle(pool)
    return pool[:max(0, n)]


def render_episode(ep, tokenizer, train_tool_turns=False):
    """Return (input_ids, labels) with everything except the assistant reply
    masked out (-100) so the adapter trains to *produce* verified answers.

    Handles multi-turn conversations (tool calls and results): the last
    assistant message is the answer, everything before it is the prompt.

    With `train_tool_turns=True` every assistant turn of a **teacher** trace is
    labeled, so the adapter also learns to *emit* the tool calls (the ReAct
    protocol), not just the final answer after them. Two guards keep this
    honest: the trace must be teacher-authored (student self-play emits noisy
    tool calls) and every tool call must actually execute in the sandbox.
    Off by default: format discipline first, one variable at a time.
    """
    msgs = ep["messages"]
    # find the last assistant message
    last_assistant = None
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i]["role"] == "assistant":
            last_assistant = i
            break
    if last_assistant is None:
        return [], []

    if (train_tool_turns and ep.get("attempt_kind") == "teacher"
            and sum(m["role"] == "assistant" for m in msgs) > 1):
        msgs = msgs[:last_assistant + 1]
        if not _tool_calls_ok(msgs):
            # unverified/broken tool calls -> answer-only, never teach them
            return render_episode({"messages": msgs}, tokenizer, False)
        try:
            text = tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False,
                enable_thinking=False)
            enc = tokenizer(text, add_special_tokens=False,
                            return_offsets_mapping=True)
            ids, offs = enc["input_ids"], enc["offset_mapping"]
            # Locate each assistant turn's character span in the rendered text.
            # ChatML: a turn runs until the next <|im_start|> marker, which also
            # covers the closing <|im_end|> the model must learn to emit.
            spans, cursor = [], 0
            for m in msgs:
                if m["role"] != "assistant" or not m["content"]:
                    continue
                s = text.find(m["content"], cursor)
                if s < 0:
                    continue
                e = s + len(m["content"])
                nxt = text.find("<|im_start|>", e)
                e = nxt if nxt != -1 else len(text)
                spans.append((s, e))
                cursor = e
            labels = [-100] * len(ids)
            for s, e in spans:
                for k, (a, b) in enumerate(offs):
                    if b > s and a < e:
                        labels[k] = ids[k]
            if not any(l != -100 for l in labels):
                raise ValueError("no assistant span located")
            return ids, labels
        except Exception:
            # template without per-turn markers -> answer-only fallback
            return render_episode({"messages": msgs}, tokenizer, False)

    prompt_msgs = msgs[:last_assistant]
    answer = msgs[last_assistant]["content"]
    # render to string then tokenize by hand: transformers' GGUF tokenizers
    # mis-tokenize in apply_chat_template(tokenize=True)
    prompt_text = tokenizer.apply_chat_template(
        prompt_msgs, tokenize=False, add_generation_prompt=True,
        enable_thinking=False)
    full_text = tokenizer.apply_chat_template(
        msgs[:last_assistant + 1], tokenize=False, add_generation_prompt=False,
        enable_thinking=False)
    prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
    full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"]
    p = len(prompt_ids)
    full = list(full_ids)
    if p >= len(full):
        p = 0
    labels = [-100] * p + full[p:]
    return full, labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--ctx", type=int, default=512)
    ap.add_argument("--max-per-family", type=int, default=200)
    ap.add_argument("--out", default=None)
    ap.add_argument("--since-merge", action="store_true",
                    help="train only on episodes appended after the last merge")
    ap.add_argument("--since-line", type=int, default=None,
                    help="train on episodes after this buffer line instead of "
                         "the merge marker (to re-train a consumed delta)")
    ap.add_argument("--kl-max", type=float, default=0.5,
                    help="peak KL-to-base penalty (liminal training, ACL 2026); "
                         "annealed to 0 by the end")
    ap.add_argument("--kl-floor", type=float, default=0.05,
                    help="minimum KL weight kept through the end (prevents the "
                         "late-step drift that collapsed train-15)")
    ap.add_argument("--no-balance", action="store_true",
                    help="do not backfill a missing skill (code/answer) from the buffer")
    ap.add_argument("--stop-loss", type=float, default=0.3,
                    help="early-stop when the 50-step rolling CE falls below this "
                         "(guards against overfitting a tiny delta)")
    ap.add_argument("--replay", type=int, default=0,
                    help="mix N pre-merge episodes into training to prevent "
                         "catastrophic forgetting (rehearsal)")
    ap.add_argument("--train-tool-turns", action="store_true",
                    help="label every assistant turn (tool calls included), "
                         "not just the final answer — teaches emitting tools")
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    install_fp32_gemm_fallback()
    install_chunked_cross_entropy()
    since_line = 0
    marker = config.DATA / "last-merge.txt"
    if args.since_merge and marker.exists():
        since_line = int(marker.read_text().strip() or 0)
    if args.since_line is not None:
        since_line = args.since_line
    eps, skipped = load_replay(args.max_per_family, since_line=since_line)
    if not eps:
        print("replay buffer empty - nothing to train on", file=sys.stderr)
        return
    full_eps = None
    if not args.no_balance or args.replay > 0:
        full_eps, _ = load_replay(args.max_per_family, since_line=0)
    if not args.no_balance:
        eps, n_bf = balance_eps(eps, full_eps)
        if n_bf:
            print(f"balance: backfilled {n_bf} episodes from the buffer to "
                  f"restore code/answer skill coverage")
    if args.replay > 0 and full_eps is not None:
        old = rehearse(eps, full_eps, args.replay)
        if old:
            eps = eps + old
            print(f"rehearsal: mixed {len(old)} pre-merge episodes to prevent "
                  f"forgetting")
    print(f"replay: {len(eps)} verified episodes (since line {since_line})"
          + (f" [{skipped} malformed skipped]" if skipped else ""))

    # train from the newest accumulated merge (the champion), not the stale
    # config snapshot: the delta window already excludes everything before it
    base = current_base()
    print(f"training base: {base}")
    tokenizer = AutoTokenizer.from_pretrained(str(base))
    model = AutoModelForCausalLM.from_pretrained(
        str(base), dtype=torch.bfloat16)
    # base weights stay bf16 (mmap-backed); all linear math runs fp32 via the
    # patch above. LoRA adapters get fp32 params for exact optimizer states.
    model.config.use_cache = False
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

    data = []
    for ep in eps:
        try:
            ids, labels = render_episode(ep, tokenizer, args.train_tool_turns)
        except Exception:
            continue
        if len(ids) <= 8 and len(labels) <= 8:
            continue
        ids, labels = ids[:args.ctx], labels[:args.ctx]
        data.append((ids, labels))
    if not data:
        print("no renderable episodes", file=sys.stderr)
        return
    print(f"trainable sequences: {len(data)}")

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=args.lr, weight_decay=0.0)
    total = args.epochs * len(data)
    step, warm = 0, max(5, total // 20)
    rng = random.Random(7)

    t0 = datetime.datetime.now()
    losses = []
    train_losses = []
    stop = False
    for epoch in range(args.epochs):
        if stop:
            break
        order = list(range(len(data)))
        rng.shuffle(order)
        for i in order:
            ids, labels = data[i]
            x = torch.tensor([ids])
            y = torch.tensor([labels])
            # cosine decay with warmup
            lr_scale = step / warm if step < warm else \
                0.5 * (1 + math.cos(math.pi * step / max(1, total - warm)))
            for g in opt.param_groups:
                g["lr"] = args.lr * max(0.05, lr_scale)
            # liminal training (ACL 2026): annealed KL-to-base leash. Strong
            # early (prevents drift/forgetting), relaxed to 0 by the end.
            # The base forward runs with adapters disabled -- same weights,
            # no extra model in memory.
            kl_w = max(args.kl_floor,
                       args.kl_max * max(0.0, 1.0 - step / max(1, total * 0.7)))
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
            ce = out.loss.item()
            kl_val = kl.item() if kl_w > 0 else 0.0
            train_loss = ce + kl_w * kl_val
            losses.append(ce)
            train_losses.append(train_loss)
            step += 1
            if step % 5 == 0:
                el = (datetime.datetime.now() - t0).total_seconds()
                rss = int(open("/proc/self/status").read()
                          .split("VmRSS:")[1].split()[0]) // 1024
                print(f"step {step}/{total} ce {sum(losses[-50:])/len(losses[-50:]):.3f} "
                      f"kl {kl_val:.4f} loss {train_loss:.3f} "
                      f"rss {rss}MB ({el/step:.1f}s/step)", flush=True)
                roll = sum(losses[-50:]) / len(losses[-50:])
                if roll < args.stop_loss and step > warm:
                    print(f"early stop: rolling ce {roll:.3f} < {args.stop_loss} "
                          f"at step {step}/{total}", flush=True)
                    stop = True
                    break

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out or str(config.ADAPTERS / f"peft-{ts}")
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    print(f"saved peft adapter -> {out_dir}")
    print(f"final ce {sum(losses[-50:])/len(losses[-50:]):.3f} "
          f"train_loss {sum(train_losses[-50:])/len(train_losses[-50:]):.3f}")


if __name__ == "__main__":
    main()
