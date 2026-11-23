#!/bin/sh
# Convert a peft adapter to GGUF, serve it on v3, run the regression eval.
# Usage: tools/gate_eval.sh <peft_dir> <label>
# Then gate: .venv/bin/python -m nexus.gate <before.json> <cand-<label>-<ts>.json>
set -e
cd "$(dirname "$0")/.."
PEFT="$1"; LABEL="${2:-cand}"
CAND="adapters/candidate-$LABEL.gguf"
PY=".venv/bin/python"

echo "== convert $PEFT -> $CAND"
$PY tools/convert_lora_to_gguf.py --base models/qwen3-1.7b-hf --outtype q8_0 \
    --outfile "$CAND" "$PEFT" >/dev/null 2>&1
test -f "$CAND" || { echo "conversion failed"; exit 1; }

echo "== serve v3 + $LABEL"
pkill -x llama-server 2>/dev/null || true; sleep 3
nohup llama-server -m models/nexus-current.gguf --host 127.0.0.1 --port 8080 \
    --ctx-size 4096 --parallel 1 --threads 8 --threads-batch 8 --jinja \
    --lora "$CAND" > "data/server-$LABEL.log" 2>&1 &
sleep 12
pgrep -x llama-server >/dev/null || { echo "server failed"; exit 1; }

echo "== regression eval ($LABEL)"
$PY -m nexus.eval run --suite regression --label "cand-$LABEL"