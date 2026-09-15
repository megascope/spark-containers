#!/bin/sh
set -eu

: "${LLAMA_API_KEY:?LLAMA_API_KEY is required}"

python3 /app/discover-models.py --models-dir /models --hf-cache-dir /hf-cache \
  --output-dir /tmp/llama-discovery

set -- \
  --models-preset /tmp/llama-discovery/models.ini \
  --models-max "${LLAMA_MODELS_MAX:-1}" \
  --offline \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key "${LLAMA_API_KEY}" \
  --ctx-size "${LLAMA_CONTEXT_SIZE:-8192}" \
  --n-gpu-layers "${LLAMA_GPU_LAYERS:-999}" \
  --flash-attn "${LLAMA_FLASH_ATTN:-on}"

exec /app/llama-server "$@"
