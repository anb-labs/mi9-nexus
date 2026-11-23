#!/bin/sh
# Nightly growth loop (whitepaper Ch. 4.3 + Ch. 7 Phase 3, scaled to CPU):
#   1. regression eval (before)                      -> reports/
#   2. self-play: generate verified traces           -> data/replay.jsonl
#   3. stop server; LoRA distill winners (PEFT/CPU)  -> adapters/peft-<ts>/
#   4. convert adapter to GGUF (q8_0)
#   5. restart server + adapter; regression gate     -> promote or rollback
#   6. on promote: merge champion into base (cumulative) + re-serve
#   7. post-adoption frozen eval                     -> reports/
# Strictly user-initiated until the safety review (Ch. 6.5).
set -e
cd "$(dirname "$0")/.."
MINUTES="${MINUTES:-45}"
TS="$(date +%Y%m%d-%H%M%S)"
PEFT_DIR="adapters/peft-$TS"
CAND="adapters/candidate-$TS.gguf"
PY=".venv/bin/python"

stop_server() {
  for pid in $(pgrep -x llama-server); do kill "$pid" 2>/dev/null || true; done
  sleep 3
}
start_server() {
  nohup nexus/serve > "data/server-$TS.log" 2>&1 &
  sleep 12
}

echo "== [1/7] regression eval (before)"
$PY -m nexus.eval run --suite regression --label nightly-before-$TS

echo "== [2/7] self-play ($MINUTES min budget)"
$PY -m nexus.selfplay --minutes "$MINUTES"

echo "== [3/7] LoRA distillation (server paused)"
stop_server
$PY -m nexus.train
PEFT=$(ls -dt adapters/peft-* | head -1)
test -d "$PEFT" || { echo "no adapter produced; restarting server"; start_server; exit 0; }

echo "== [4/7] convert adapter -> GGUF"
$PY tools/convert_lora_to_gguf.py --base models/qwen3-1.7b-hf --outtype q8_0 \
    --outfile "$CAND" "$PEFT"
test -f "$CAND" || { echo "conversion failed; restarting server"; start_server; exit 1; }

echo "== [5/7] regression gate on candidate adapter"
start_server --lora "$CAND"
$PY -m nexus.eval run --suite regression --label nightly-candidate-$TS
BEFORE=$(ls -t reports/nightly-before-$TS-*.json | head -1)
CANDR=$(ls -t reports/nightly-candidate-$TS-*.json | head -1)
KEEP=$($PY -m nexus.gate "$BEFORE" "$CANDR")

stop_server
if [ "$KEEP" = "1" ]; then
  echo "== [6/7] gate PASSED - merging candidate into the accumulated base"
  $PY -m nexus.merge --champion "$PEFT"
  MERGED=$(ls -dt models/merged-* | head -1)
  PYTHONPATH=tools/llama-gguf-py $PY tools/convert_hf_to_gguf.py "$MERGED" --outfile "$MERGED/f16.gguf" >/dev/null 2>&1 || true
  if [ -f "$MERGED/f16.gguf" ]; then
    llama-quantize --allow-requantize "$MERGED/f16.gguf" "models/mi9-nexus-$TS-Q8_0.gguf" Q8_0
    ln -sf "mi9-nexus-$TS-Q8_0.gguf" models/nexus-current.gguf
    rm -f "$MERGED/f16.gguf"
  fi
  start_server
else
  echo "== [6/7] gate FAILED - automatic rollback (candidate discarded)"
  rm -f "$CAND"
  start_server
fi

echo "== [7/7] post-adoption frozen eval"
$PY -m nexus.eval run --suite frozen --label nightly-after-$TS
echo "nightly cycle complete ($TS)"
