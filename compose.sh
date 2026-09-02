#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Usage: ./compose.sh FOLDER [docker compose arguments...]

Examples:
  ./compose.sh llama.cpp up -d --build
  ./compose.sh litellm logs -f
  ./compose.sh nextchat down
EOF
}

if [ "$#" -lt 2 ]; then
  usage >&2
  exit 2
fi

folder=$1
shift

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="${repo_dir}/${folder}/compose.yaml"
env_file="${repo_dir}/.env"

case "$folder" in
  ""|/*|.|..|*/../*|../*|*/..)
    echo "Invalid project folder: ${folder}" >&2
    exit 2
    ;;
esac

if [ ! -f "$compose_file" ]; then
  echo "Compose file not found: ${compose_file}" >&2
  exit 2
fi

if [ ! -f "$env_file" ]; then
  echo "Environment file not found: ${env_file}" >&2
  echo "Create it with: cp ${repo_dir}/.env.example ${env_file}" >&2
  exit 2
fi

exec docker compose --env-file "$env_file" -f "$compose_file" "$@"
