# Local LLM serving on DGX Spark

This repository runs four independently managed Compose projects:

- `llama.cpp`: CUDA-backed GGUF/VLM inference.
- `vllm`: optional HF Safetensors/NVFP4 inference; see [setup and cache discovery](vllm/README.md).
- `litellm`: an authenticated OpenAI-compatible proxy in front of llama.cpp and optional vLLM/Ollama services, with a temporary Postgres database for its built-in playground.
- `nextchat`: an optional browser UI, configured to use LiteLLM.

All four join one pre-created, internal Docker network for service-to-service traffic. Each service also gets a project-local bridge network so Docker can publish its host port. Each host port is bound to a configurable interface; the defaults are localhost only.

## Model discovery

llama.cpp runs in its native router mode. These two `.env` paths are independent
and optional:

```dotenv
MODELS_DIR=/srv/models
HF_CACHE_DIR=~/.cache/huggingface/hub
```

Leave either blank to disable that source. With both blank, the router has an
empty model catalog. A configured directory must already exist; Compose will
not create it on a typo. Both sources are mounted read-only.

At startup, `llama.cpp/discover-models.py` recursively finds GGUF files in both
sources and generates a llama.cpp preset under `/tmp`. This supports the standard
Hugging Face `hub` cache (or its parent), including snapshot symlinks into `blobs`.
Mount the whole cache so those relative symlinks resolve. Absolute symlinks outside
the container mounts and directory symlinks are not supported. No models are
downloaded, converted, or copied; only temporary symlinks and configuration are
created. Safetensors/PyTorch checkpoints need conversion to a supported GGUF first.

Each quantization is listed separately. Split GGUFs are registered once, using
their first shard, and incomplete sets are skipped with a log message. Duplicate
resolved model/projector paths are registered once, preferring `MODELS_DIR`.
Models still need architectures supported by the pinned llama.cpp version;
discovery checks file readability and the GGUF header, not full compatibility.

For vision, keep a compatible `mmproj*.gguf` beside its model (or quantizations
of that same model). Exactly one projector in that directory is attached
automatically. With multiple projectors, discovery logs a warning and serves
the model without vision; separate the matching pairs into different folders.
Projectors and files named `draft-*` or `mtp-*` are not standalone model entries.

Model IDs use `models/<relative-path-without-.gguf>` or
`hf/<relative-path-without-.gguf>`. Special characters are percent-encoded;
HF IDs include the snapshot revision. Query the catalog for the exact ID:

```bash
curl -fsS "http://${LLAMA_LISTEN_ADDR:-127.0.0.1}:${LLAMA_PORT:-8000}/v1/models" \
  -H "Authorization: Bearer ${LLAMA_API_KEY}"
```

These commands assume `.env` variables are exported in your shell. Send the
selected ID in the request's `model` field. Weights load on demand;
`LLAMA_MODELS_MAX=1` limits resident models by default. Increase it only when
the models and their context buffers fit together in available memory.
`/health` checks the router; successful inference verifies an individual model.

After adding or removing files, restart llama.cpp to rebuild the catalog.
After changing mount paths, recreate the container:

```bash
./compose.sh llama.cpp up -d --build --force-recreate
./compose.sh llama.cpp logs -f
```

### Migrating the previous single-model setup

`MODEL_FILE` and `MMPROJ_FILE` are no longer used. Keep `MODELS_DIR`, optionally
add `HF_CACHE_DIR`, and rebuild llama.cpp. The existing CUDA/ARM64 build and
authentication remain in place. The pinned `v0.4.1` supports
[router mode](https://github.com/ggml-org/llama.cpp/blob/v0.4.1/tools/server/README.md#using-multiple-models).

For LiteLLM, update existing `.env` files to pass model IDs through:

```dotenv
LITELLM_MODEL=openai/*
LLAMA_CPP_MODEL_NAME=*
```

Then recreate LiteLLM with `./compose.sh litellm up -d`. Through LiteLLM, request
`openai/<llama.cpp-model-id>`. A fixed alias can still be used by setting
`LLAMA_CPP_MODEL_NAME` to one actual discovered ID. NextChat's static model picker
needs concrete IDs; a wildcard is not a selectable model. Configure its model
list for the discovered IDs if using that UI.

## Prerequisites

- DGX Spark / ARM64 with the NVIDIA container runtime working.
- Docker Engine with Compose 2.20.0 or newer.
- A compatible GGUF model and, for a vision model, its matching `mmproj` file.

The pinned LiteLLM and NextChat images both publish native `linux/arm64` variants. llama.cpp is built locally from the pinned `LLAMA_CPP_REF` for CUDA architecture 12.1 (GB10).

## Configure

From the repository root:

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and replace all `change-me` secrets. Optionally set `MODELS_DIR`,
`HF_CACHE_DIR`, or both to absolute host directory paths (see below).

`LLAMA_API_KEY` protects the llama.cpp backend from other containers on the shared network. `LITELLM_MASTER_KEY` protects the client-facing LiteLLM API and is supplied to NextChat. `NEXTCHAT_ACCESS_CODE` protects the UI.

Set `LLAMA_API_BASE` to the OpenAI-compatible upstream URL reachable from the LiteLLM container, including `/v1`. It defaults to `http://llama-server:8000/v1`; it can also point to Unsloth or another OpenAI-compatible server. `LLAMA_API_KEY` is the key for that upstream.

If an external upstream has authentication disabled, `LLAMA_API_KEY` may be
blank or omitted. LiteLLM receives the non-secret placeholder `not-required`
because its OpenAI model-discovery client always sends a Bearer header and an
empty token produces an invalid HTTP header. Authenticated upstreams still need
their real key; the bundled llama.cpp project still requires its configured key.

Optionally set `OLLAMA_API_BASE` to the Ollama server URL reachable from the LiteLLM container (for example, `http://ollama-host:11434`). Leave it blank or omit it to disable Ollama routes and discovery. At startup, `litellm/start.py` removes those routes from a temporary copy of the configuration in `/tmp` before running the upstream entrypoint; the mounted configuration stays unchanged. Recreate LiteLLM after changing the setting.

To disable the NextChat UI access code, leave `NEXTCHAT_ACCESS_CODE` blank or remove it from `.env`, then recreate NextChat with `./compose.sh nextchat up -d`. Anyone who can reach the UI can then use its configured backend.

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

## Use the LiteLLM playground without NextChat

Postgres starts by default with LiteLLM and supplies the database required by the
[LiteLLM admin UI](https://docs.litellm.ai/docs/proxy/ui). Postgres runs on a
project-private internal network with no published port. The pinned official
Postgres image supports native ARM64.

Generate a password with `openssl rand -hex 32`, then add these settings to `.env`
(use the generated hex password so it is URL-safe):

```dotenv
LITELLM_POSTGRES_PASSWORD=replace-with-generated-hex-password
```

LiteLLM constructs `DATABASE_URL` automatically from this password. An existing
`DATABASE_URL` override is still honored; remove it to use the automatic URL.

Start LiteLLM after starting your inference backend:

```bash
./compose.sh litellm up -d
./compose.sh litellm ps
./compose.sh litellm logs -f
```

LiteLLM waits for Postgres to become healthy and initializes its database schema
at startup. Open `http://127.0.0.1:4000/ui` (or your configured LiteLLM address and
port), sign in as `admin` using `LITELLM_MASTER_KEY` as the password, and select
the model playground. Use `LITELLM_UI_USERNAME` and `LITELLM_UI_PASSWORD` in `.env`
to override those credentials. NextChat is unnecessary; if it is already running,
stop it with `./compose.sh nextchat down`.

Database storage is tmpfs, limited by `LITELLM_POSTGRES_TMPFS_SIZE` (default `1g`).
**Stopping, restarting, or recreating Postgres erases all database state**, including
UI-created keys and settings. Models and the file-based LiteLLM configuration are
unaffected. Keep lasting model routes in `litellm/config.yaml`. Tmpfs can use host
swap; it is ephemeral storage, not a guarantee that bytes never reach disk.

After a database restart, restart LiteLLM too so it recreates the schema. For a
deliberate reset, stop and start the whole project:

```bash
./compose.sh litellm down
./compose.sh litellm up -d
```

If startup or UI login fails, inspect both services' logs for password or schema
migration errors. Ensure `LITELLM_POSTGRES_PASSWORD` is set and any
`DATABASE_URL` override uses the matching password and `postgres:5432`. If the tmpfs fills, increase its size in `.env` and
recreate the project; this also discards the old database. After an unexpected
Postgres restart, restart LiteLLM to rebuild missing tables.

Postgres is a required dependency of LiteLLM. `./compose.sh litellm down` stops
both services. No database directory or volume needs deleting.

## Unsloth upstream and wildcard routing

To use [Unsloth's OpenAI-compatible API](https://unsloth.ai/docs/basics/api), set
these values in `.env`, replacing the host and API key:

```dotenv
LLAMA_API_BASE=http://unsloth-host:8888/v1
LLAMA_API_KEY=replace-with-your-unsloth-api-key
LITELLM_MODEL=openai/*
LLAMA_CPP_MODEL_NAME=*
```

This uses [LiteLLM wildcard routing](https://docs.litellm.ai/docs/wildcard_routing)
to forward `openai/<upstream-model-id>` requests to Unsloth with the `openai/`
prefix removed. You do not need a separate LiteLLM route for each model.
Despite its historical name, `LLAMA_CPP_MODEL_NAME` applies to whichever
OpenAI-compatible server `LLAMA_API_BASE` selects. The Ollama route is separate.

The existing `check_provider_endpoint: true` setting enables upstream model
discovery for `/v1/models`. Unsloth lists its **currently loaded models**, not
every downloaded model. Load the model in Unsloth first, then query LiteLLM's
`/v1/models` using the command in "Test LiteLLM" and select a concrete model ID
in the playground. Do not send the literal `openai/*` as a model name. Discovery
and wildcard request routing are separate: clients with a static model picker
may still need their own configuration; the NextChat helper only discovers
Ollama models.

Recreate LiteLLM after changing `.env`:

```bash
./compose.sh litellm up -d
```

When using external Unsloth,
the local llama.cpp project does not need to run. Keep Unsloth reachable over
your private network; `localhost` inside LiteLLM refers to its own container.
For a single fixed alias instead of wildcards, retain `LITELLM_MODEL=local-llama`
and set `LLAMA_CPP_MODEL_NAME` to the exact model ID Unsloth advertises.

## Add Ollama models to NextChat

With `OLLAMA_API_BASE` set, an `ollama_chat/*` route and `check_provider_endpoint: true` configured in
`litellm/config.yaml`, use the Python 3 helper to query the running LiteLLM
service and add its discovered Ollama models to NextChat's picker:

```bash
ollama_export=$(python3 litellm/ollama-models.py) &&
  eval "$ollama_export" &&
  ./compose.sh nextchat up -d
```

The helper prints only a shell-quoted `export OLLAMA_MODELS=...` on success.
It selects IDs starting with `ollama_chat/`, adds NextChat's `+` marker, removes
duplicates, and sorts them. The existing local model stays in the picker.
Errors go to stderr with a nonzero exit status, so the command above does not
apply a failed lookup. An empty inventory exports an empty value.
Wildcard route entries such as `ollama_chat/*` are skipped. If LiteLLM returns
only Ollama wildcard routes without any concrete Ollama models, the helper fails
with a discovery diagnostic instead of clearing the existing export.

`OLLAMA_MODELS` defaults to empty and is appended to the existing local model.
The export overrides `.env` for the current shell; rerun the command when the
Ollama inventory changes, then refresh NextChat. Alternatively, save the generated
value as `OLLAMA_MODELS=...` in `.env` for future Compose invocations.
The helper uses `compose.sh litellm exec` to request `/v1/models` inside the
running LiteLLM container, using its existing master key. No endpoint argument
or separate credentials are needed; the Ollama endpoint stays in LiteLLM's
configuration. Run it on the Docker host with Python 3 and Compose available.
After changing LiteLLM's configuration, restart LiteLLM before running the helper.
Only LiteLLM needs network access to Ollama. The discovered list can include
embedding-only models; omit those if maintaining the list manually.

## Security and persistence

- llama.cpp and LiteLLM use upstream non-root runtimes; NextChat is forced to UID/GID 65534 because its upstream image otherwise defaults to root.
- Every service drops all Linux capabilities, enables `no-new-privileges`, uses a read-only root filesystem, and receives only small tmpfs mounts needed at runtime.
- The shared backend network is internal. Project-local ingress bridges exist solely to support host port publishing; like ordinary Docker bridge networks, they also permit outbound connections from the containers.
- Models are bind-mounted read-only and are never copied into an image.
- LiteLLM starts with Postgres by default, storing its database in tmpfs with no persistent volume; Redis is not required. Postgres runs as UID/GID 999 with the same capability and filesystem restrictions as the other services.
- The pinned NextChat release is intended here only for trusted private clients. Do not publish it directly to the internet.

## Upgrade

Update the pinned image tag in the relevant Compose file, verify that its manifest still includes `linux/arm64`, then pull and recreate that project. To upgrade llama.cpp, update `LLAMA_CPP_REF` in `.env`, review upstream changes, and rebuild it.

## Remove

Bring down the projects using the commands above; `./compose.sh litellm down` also removes Postgres. When no other project uses the network:

```bash
docker network rm spark-llm
```

This does not remove anything under `MODELS_DIR` or `HF_CACHE_DIR`. Images can be removed separately with `docker image rm` if desired.
