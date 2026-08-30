#!/bin/bash
# assumes llm tool (uv tool install llm)
llm openai endpoint http://127.0.0.1:8001/v1 \
  -m "$(curl -s http://127.0.0.1:8001/v1/models | jq -r '.data[0].id')" \
  --chat
