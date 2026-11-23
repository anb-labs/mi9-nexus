# Mi9-Nexus

A scaled-to-this-laptop implementation of the **Mi9-Nexus** research program
(`Beyond_the_Whole_Internet_NEXUS-14_Whitepaper-1.pdf`). The whitepaper's
thesis: intelligence and knowledge are separable — reasoning is trained with
RL on **verifiable** tasks, knowledge stays **on disk**, precision is
**outsourced to an executor**, and growth **compounds nightly** on the user's
own experience.

This machine (i7-8565U, UHD 620 iGPU, 7.4 GB RAM) is below the whitepaper's
16 GB-VRAM target, so the architecture is scaled down faithfully rather than
abandoned: the reasoning core is a 1.5–4B class model on CPU instead of a 14B
hybrid on a GPU. Every component principle is preserved.

## Components (whitepaper mapping)

| Mi9-Nexus (Ch. 4, Table 2)            | Mi9-Nexus here                                        |
|--------------------------------------|----------------------------------------------------------|
| 14B hybrid core, 4-bit, dual-mode    | Qwen3-1.7B Q4_K_M via llama.cpp (dual-mode: /think//no_think) |
| int8 KV, 16–32K context              | Q8_0 KV option (`KV_Q8=1`), 8K context, 1 slot           |
| grounded memory 20–60 GB corpus      | `corpus/` + SQLite FTS BM25 hybrid retrieval, citations  |
| verifier stack (executor, tests)     | `nexus/sandbox.py`: unshare-network sandbox, rlimits     |
| budget scheduler                     | `enable_thinking:false` fast path vs `/think` deep path  |
| nightly growth loop + rollback       | STaR/AZR self-play → PEFT LoRA → GGUF → regression gate  |
| cumulative growth (no forgetting)    | merge-and-carry: champion LoRA baked into base each cycle |

Measured on this box (throughput audit, whitepaper §5.3): **16.5 tok/s**
decode on the 1.7B Q4 core — ~78% of the bandwidth÷weight-bytes arithmetic
(34 GB/s LPDDR3 × 0.65 efficiency / 1.05 GB weights ≈ 21 tok/s).

## Layout

```
models/      GGUF weights (downloaded)
corpus/      your curated knowledge (drop .md/.txt/... here)
data/        replay.jsonl (verified wins), episodes.jsonl (all attempts), curriculum
suites/      frozen eval + regression gate (locked, contamination-proof)
adapters/    nightly LoRA outputs (promoted ones survive)
reports/     eval JSON reports
nexus/       the code
```

## Usage

```sh
# 1. serve the reasoning core
nexus/serve &

# 2. frozen suites + regression gate (once)
python3 -m nexus.eval freeze

# 3. baseline capability probe (before any training)
python3 -m nexus.eval run --suite frozen --label baseline

# 4. talk to it (retrieval + executor tools, evidence-labeled answers)
python3 -m nexus.chat --ask "what is 17*23? verify with code"
python3 -m nexus.chat

# 5. index your corpus for grounded memory
python3 -m nexus.memory index
python3 -m nexus.memory query "how do I reset the GNOME keyring"

# 6. the nightly growth loop (user-initiated; MINUTES env for self-play budget)
MINUTES=45 nexus/nightly.sh
```

Self-play alone: `python3 -m nexus.selfplay --minutes 20`.
Agentic self-play (ReAct tool-use traces): `python3 -m nexus.agentic --minutes 20`.

Training: the packaged `llama-finetune` in Arch's llama-cpp 0.9.0 does
full-parameter fp32 finetuning (~24 GB, "for FP32 models" per upstream docs) —
not viable on 7.4 GB RAM. The nightly distiller therefore uses **PEFT LoRA on
CPU** (`nexus/train.py`, frozen Q8_0 base read directly by transformers' GGUF
loader, ~4 GB peak), converts the adapter with llama.cpp's
`tools/convert_lora_to_gguf.py`, and serves it with
`llama-server --lora <adapter.gguf>`. Full loop: `MINUTES=45 nexus/nightly.sh`.

## How "getting smarter" is measured

The whitepaper's Phase-0 gate is a **reproducible harness with measured
variance**. Here: `reports/*.json` — weekly pass@1 on the frozen suite
(capability trend) and the regression suite (no-forgetting gate). Growth is
only "real" if frozen pass@1 rises and regression stays within the gate.

## Status / roadmap

- [x] verifier stack (network-isolated sandbox, rlimits, test harness)
- [x] 27 self-generating task families (code/math/logic + math-via-executor + data wrangling)
- [x] STaR/AZR self-play collector with AZR difficulty curriculum
- [x] frozen + regression suites (Phase-0 harness)
- [x] grounded memory (BM25 hybrid over the local corpus)
- [x] chat runtime with tool belt + evidence labels (run_python captures stdout)
- [x] LoRA distiller (PEFT CPU) + GGUF conversion + regression gate + nightly orchestrator
- [x] throughput audit vs. whitepaper §5.3 arithmetic (16.5 tok/s measured, ~78% of theory)
- [x] baseline eval + first self-play cycle (58.5% → 70.5% frozen, gate passed)
- [x] first nightly LoRA distillation + gate demonstration (cycle 2 rolled back: gate works)
- [x] cumulative merge-and-carry architecture (champion baked into base, no forgetting)
- [x] schema extraction: 34 playbooks from verified traces, indexed in FTS5
- [x] agentic self-play: ReAct-style tool-use traces (run_python + retrieve)
- [x] tool-use training cycle: model now emits run_python calls in chat (v3)
- [ ] continued pre-training on a real code/reasoning corpus (raw data → weights)
- [ ] optional: EAGLE-style speculative decoding, Vulkan iGPU offload
