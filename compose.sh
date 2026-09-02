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

prepare_networks=false
for arg in "$@"; do
  if [ "$arg" = "up" ]; then
    prepare_networks=true
    break
  fi
done

if [ "$prepare_networks" = "true" ]; then
  network_names=$(
    docker compose --env-file "$env_file" -f "$compose_file" config |
      awk '$0 == "networks:" { in_networks=1; next }
           in_networks && /^  [^ ].*:$/ {
             network=$1
             sub(/:$/, "", network)
             next
           }
           in_networks && $1 == "name:" { names[network]=$2 }
           in_networks && $1 == "external:" && $2 == "true" {
             external[network]=1
           }
           END {
             for (network in external) print names[network]
           }'
  )

  for network_name in $network_names; do
    if internal=$(docker network inspect --format '{{.Internal}}' "$network_name" 2>/dev/null); then
      if [ "$internal" != "true" ]; then
        echo "Docker network ${network_name} exists but is not internal." >&2
        echo "Refusing to attach the LLM services to a network with external egress." >&2
        exit 1
      fi
    else
      docker network create --internal "$network_name" >/dev/null
      echo "Created internal Docker network: ${network_name}"
    fi
  done
fi

exec docker compose --env-file "$env_file" -f "$compose_file" "$@"
