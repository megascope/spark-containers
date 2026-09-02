#!/bin/sh
set -eu

: "${MODEL_FILE:?MODEL_FILE is required}"
: "${LLAMA_API_KEY:?LLAMA_API_KEY is required}"

set -- \
  --model "/models/${MODEL_FILE}" \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key "${LLAMA_API_KEY}" \
  --ctx-size "${LLAMA_CONTEXT_SIZE:-8192}" \
  --n-gpu-layers "${LLAMA_GPU_LAYERS:-999}" \
  --flash-attn "${LLAMA_FLASH_ATTN:-on}"

if [ -n "${MMPROJ_FILE:-}" ]; then
  set -- "$@" --mmproj "/models/${MMPROJ_FILE}"
fi

exec /app/llama-server "$@"
