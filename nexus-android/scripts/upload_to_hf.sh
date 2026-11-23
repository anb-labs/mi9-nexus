#!/usr/bin/env bash
# Upload the Mi9-Nexus GGUF to HuggingFace.
#
# Usage: ./scripts/upload_to_hf.sh <hf-username>/mi9-nexus
#
# Requires auth once:  hf auth login --token hf_xxx   (or export HF_TOKEN=hf_xxx)
# The `hf` CLI ships with huggingface_hub (https://huggingface.co/docs/huggingface_hub).
set -euo pipefail
cd "$(dirname "$0")/.."

REPO="${1:?usage: upload_to_hf.sh <hf-username>/mi9-nexus}"
MODEL="/home/santosh/Mi9/mi9-ai-model/models/mi9-nexus-v3-Q8_0.gguf"

[ -f "$MODEL" ] || { echo "model not found: $MODEL" >&2; exit 1; }
command -v hf >/dev/null || { echo "install: pip install -U huggingface_hub" >&2; exit 1; }

echo "==> repo: $REPO"
echo "==> model: $MODEL ($(du -h "$MODEL" | cut -f1))"

# Create the repo if it doesn't exist (ignore error if it already does).
hf repo create "$REPO" --type model -y 2>/dev/null || true

# Upload the GGUF (and a model card if present).
hf upload "$REPO" "$MODEL" "mi9-nexus-v3-Q8_0.gguf" \
  --commit-message "Upload Mi9-Nexus v3 (Q8_0)"

echo "==> done: https://huggingface.co/$REPO"