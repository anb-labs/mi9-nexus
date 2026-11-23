"""NEXUS-Micro configuration.

Scales the NEXUS-14 whitepaper (Ch. 4, Table 2) to an 8 GB / iGPU-less laptop:
  reasoning core   -> 1.5-4B class, 4-bit, CPU  (whitepaper: 14B hybrid on 16 GB GPU)
  grounded memory  -> local corpus + hybrid retrieval (0.4% doctrine, Ch. 5.4)
  verifier stack   -> sandboxed executor (Ch. 4.2) - identical principle, smaller box
  growth loop      -> nightly STaR/AZR self-play + LoRA adapter + rollback gate (Ch. 4.3, 6.5)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODELS = ROOT / "models"
DATA = ROOT / "data"
ADAPTERS = ROOT / "adapters"
SUITES = ROOT / "suites"
REPORTS = ROOT / "reports"
CORPUS = ROOT / "corpus"
INDEX = DATA / "memory_index.sqlite3"

for d in (MODELS, DATA, ADAPTERS, SUITES, REPORTS, CORPUS):
    d.mkdir(parents=True, exist_ok=True)

# --- Reasoning core -------------------------------------------------------
BASE_MODEL = MODELS / "mi9-nexus-v3-Q8_0.gguf"  # champion-merged accumulated model (Ch. 4.3) — gate evals candidates on this base
HF_SNAPSHOT = MODELS / "merged-20261113-050149"    # training base: champion merged into base (current champion)
                                                   # + tokenizer + template (mmap-loaded; the
                                                   # transformers GGUF loader OOMs on 8 GB RAM)
DEEP_MODEL = MODELS / "Qwen3-4B-Q4_K_M.gguf"      # optional deep path (enabled if present)
EMBED_MODEL = MODELS / "bge-small-en-v1.5-Q8_0.gguf"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8080
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# --- Verifier stack -------------------------------------------------------
SANDBOX_CPU_SECONDS = 10          # per check
SANDBOX_MEM_MB = 512              # RLIMIT_AS inside the sandbox
SANDBOX_NET = False               # unshare -rn: no network, ever

# --- Growth loop ----------------------------------------------------------
SELFPLAY_TIME_BUDGET_MIN = 45     # per cycle (nightly is: this x N + training)
KEEP_RATE_WINDOW = 24             # tasks between difficulty adjustments
DIFFICULTY_UP = 0.55              # keep-rate above this -> harder tasks (AZR ZPD curriculum)
DIFFICULTY_DOWN = 0.30            # keep-rate below this -> easier

LORA_R = 16
LORA_ALPHA = 32
TRAIN_CTX = 512
TRAIN_BATCH = 256

REGRESSION_SIZE = 100             # frozen regression gate (Ch. 6.5)
EVAL_PER_FAMILY = 8               # held-out samples per family in reports
K_SAMPLES = 1                     # pass@k
TEMPERATURE = 0.7

REPLAY = DATA / "replay.jsonl"
EPISODES = DATA / "episodes.jsonl"
REGRESSION_SET = SUITES / "regression.json"
