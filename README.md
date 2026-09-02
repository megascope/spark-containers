# Local LLM serving on DGX Spark

This repository runs three independently managed Compose projects:

- `llama.cpp`: CUDA-backed GGUF/VLM inference.
- `litellm`: a stateless, authenticated OpenAI-compatible proxy in front of llama.cpp.
- `nextchat`: the browser UI, configured to use LiteLLM.

All three join one pre-created, internal Docker network for service-to-service traffic. Each service also gets a project-local bridge network so Docker can publish its host port. Each host port is bound to a configurable interface; the defaults are localhost only.

## Prerequisites

- DGX Spark / ARM64 with the NVIDIA container runtime working.
- Docker Engine with the Compose plugin.
- A compatible GGUF model and, for a vision model, its matching `mmproj` file.

The pinned LiteLLM and NextChat images both publish native `linux/arm64` variants. llama.cpp is built locally from the pinned `LLAMA_CPP_REF` for CUDA architecture 12.1 (GB10).

## Configure

From the repository root:

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env`. At minimum, set `MODELS_DIR`, `MODEL_FILE`, and replace all three `change-me` secrets. Set `MMPROJ_FILE` only for a model that needs a multimodal projection file.

`LLAMA_API_KEY` protects the llama.cpp backend from other containers on the shared network. `LITELLM_MASTER_KEY` protects the client-facing LiteLLM API and is supplied to NextChat. `NEXTCHAT_ACCESS_CODE` protects the UI.

To expose LiteLLM and NextChat on a private LAN address, for example:

```dotenv
LITELLM_LISTEN_ADDR=192.168.1.20
NEXTCHAT_LISTEN_ADDR=192.168.1.20
```

Do not use `0.0.0.0` unless every interface on the host is trusted or separately firewalled. The `.env` file and environment-specific variants are ignored by Git.

## Create the shared network

The `compose.sh` wrapper automatically creates the shared internal network the first time an `up` command is run. If you prefer to create it manually, or are not using the wrapper:

```bash
docker network create --internal spark-llm
```

The backend network is external to each Compose project, so taking any one project down does not disrupt the others. The wrapper refuses to use an existing backend network with the configured name if it is not internal. Compose creates and removes each project's ordinary ingress bridge automatically.

## Start and stop

The repository-root `compose.sh` wrapper selects the shared `.env` and the requested project's Compose file. Start the backend first:

```bash
./compose.sh llama.cpp up -d --build
./compose.sh litellm up -d
./compose.sh nextchat up -d
```

They remain independently manageable:

```bash
./compose.sh nextchat down
./compose.sh litellm down
./compose.sh llama.cpp down
```

Watch model loading and service health with:

```bash
./compose.sh llama.cpp logs -f
./compose.sh litellm ps
./compose.sh nextchat ps
```

## Test LiteLLM

```bash
set -a
. ./.env
set +a
curl -fsS "http://${LITELLM_LISTEN_ADDR}:${LITELLM_PORT}/v1/models" \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}"
```

Open `http://NEXTCHAT_LISTEN_ADDR:NEXTCHAT_PORT`, enter `NEXTCHAT_ACCESS_CODE`, and select the configured `LITELLM_MODEL`.

## Security and persistence

- llama.cpp and LiteLLM use upstream non-root runtimes; NextChat is forced to UID/GID 65534 because its upstream image otherwise defaults to root.
- Every service drops all Linux capabilities, enables `no-new-privileges`, uses a read-only root filesystem, and receives only small tmpfs mounts needed at runtime.
- The shared backend network is internal. Project-local ingress bridges exist solely to support host port publishing; like ordinary Docker bridge networks, they also permit outbound connections from the containers.
- Models are bind-mounted read-only and are never copied into an image.
- LiteLLM has no database, Redis, cache, or persistent volume; configuration is file-based and request handling is stateless.
- The pinned NextChat release is intended here only for trusted private clients. Do not publish it directly to the internet.

## Upgrade

Update the pinned image tag in the relevant Compose file, verify that its manifest still includes `linux/arm64`, then pull and recreate that project. To upgrade llama.cpp, update `LLAMA_CPP_REF` in `.env`, review upstream changes, and rebuild it.

## Remove

Bring down all three projects using the commands above. When no other project uses the network:

```bash
docker network rm spark-llm
```

This does not remove anything under `MODELS_DIR`. Images can be removed separately with `docker image rm` if desired.
