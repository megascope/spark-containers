#!/bin/bash
# Assumes llm (uv tool install llm) and jq.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a
source "${repo_dir}/.env"
set +a

base_url="http://${LITELLM_LISTEN_ADDR}:${LITELLM_PORT}/v1"
model="$(curl -fsS "${base_url}/models" \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" | jq -r '.data[0].id')"

llm openai endpoint "${base_url}" \
  --key "${LITELLM_MASTER_KEY}" \
  -m "${model}" \
  "$@"
