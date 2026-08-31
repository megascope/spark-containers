#!/bin/bash
# assumes llm tool (uv tool install llm)

source .env
llm openai endpoint http://${BIND_ADDR}/v1 \
  -m "$(curl -s http://${BIND_ADDR}/v1/models | jq -r '.data[0].id')" \
  "$*"
