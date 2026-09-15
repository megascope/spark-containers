# vLLM on DGX Spark

Serve a cached Hugging Face Safetensors checkpoint through an authenticated
OpenAI-compatible endpoint, including NVFP4 checkpoints supported by vLLM.
The Spark's GB10 GPU runs inference; application clients can run elsewhere.

## Architecture and model discovery

`LiteLLM -> vllm-server:8000 -> GB10`

The launcher scans `HF_CACHE_DIR` (the HF `hub` directory or its parent). It
lists snapshots with a model config, tokenizer and complete Safetensors weights,
following the cache's relative file symlinks without copying data. GGUF-only
repositories and adapter-only checkpoints are excluded. This is a file inventory,
not a guarantee that vLLM supports every architecture or quantization it finds.

**One vLLM process serves one base model.** If there is one candidate repository,
it is selected automatically. The complete cached `main` revision is preferred;
otherwise there must be exactly one complete revision. With several models or
ambiguous revisions, startup prints the choices and fails clearly. Set
`VLLM_MODEL=owner/repository` or `owner/repository@revision` to select one.
There is no automatic multi-model switching or loading of every cache entry.

The API model ID is `owner/repository`, without the revision. Restart/recreate
vLLM after changing the selection or updating the cache. Both GGUF and vLLM
services can read the same cache. Their memory budgets are independent.

## Prerequisites

- DGX Spark, native ARM64, working NVIDIA Container Toolkit and CUDA 13 driver.
- Docker Compose as described in the repository README.
- A complete locally downloaded checkpoint, including config, tokenizer, and
  all weight shards. For vision, include its processor configuration too.
- Read/traverse permission for container UID/GID 10001 on the cache and parents.

The pinned upstream `vllm/vllm-openai:v0.28.0` image publishes ARM64 and uses
CUDA 13.0. It provides Torch, vLLM and the GPU kernels; the Dockerfile only adds
our launcher and a non-root runtime. Model-specific GB10 kernel compatibility
still needs an inference test. No host driver modifications are performed.

Sources: [vLLM release](https://github.com/vllm-project/vllm/releases/tag/v0.28.0),
[NVIDIA Spark guide](https://github.com/NVIDIA/dgx-spark-playbooks/blob/main/nvidia/vllm/README.md).

Verified on the Spark's GB10 with driver 580.173.02: native ARM64 image build,
CUDA initialization, read-only HF discovery, and a chat completion through
LiteLLM 1.100.1 using `orcarouter/Qwen3.8-27B-Uncensored-NVFP4` revision
`69d21348b2d6c11439fb69368f40414c2256e44e`. The default 8192 context,
0.50 memory utilization and four sequences were used. Model listing and
unauthenticated-request rejection also passed. This was a text smoke test;
vision, tool calls and other checkpoints were not tested.

## Configuration and startup

Use the repository-root `.env` (and `.env.example`), not a separate project env.
For the existing Qwen cache:

```dotenv
HF_CACHE_DIR=~/.cache/huggingface/hub
# Optional if this is the only complete Safetensors model repository:
VLLM_MODEL=orcarouter/Qwen3.8-27B-Uncensored-NVFP4
VLLM_API_BASE=http://vllm-server:8000/v1
VLLM_MAX_MODEL_LEN=8192
VLLM_GPU_MEMORY_UTILIZATION=0.50
VLLM_MAX_NUM_SEQS=4
```

`VLLM_API_KEY` optionally sets a separate upstream key. Blank/omitted uses
`LLAMA_API_KEY` in both Compose projects. `LITELLM_MASTER_KEY` remains the client
key. The host endpoint defaults to `127.0.0.1:8001`; configure
`VLLM_LISTEN_ADDR`/`VLLM_PORT` for private LAN or tunnel access.

Run on the Spark so `~` resolves to the Spark user's home:

```bash
./compose.sh vllm up -d --build
./compose.sh vllm logs -f
# Enable the vLLM route after its /health endpoint is ready:
./compose.sh litellm up -d
```

Clients request `vllm/orcarouter/Qwen3.8-27B-Uncensored-NVFP4` through LiteLLM.
Existing `openai/*` routes continue to use llama.cpp. An omitted/blank
`VLLM_API_BASE` disables the vLLM route. LiteLLM's provider discovery advertises
models from the running server, not every checkpoint on disk. NextChat's static
picker needs the concrete model ID added separately.

List cached checkpoint candidates without loading weights:

```bash
./compose.sh vllm run --rm --no-deps vllm-server --list
```

`VLLM_EXTRA_ARGS` is an optional JSON array of extra upstream arguments, never
shell-evaluated. For example, if the chosen model uses the Qwen parsers:

```dotenv
VLLM_EXTRA_ARGS='["--reasoning-parser","qwen3","--enable-auto-tool-choice","--tool-call-parser","qwen3_coder"]'
```

The launcher does not force NVFP4: vLLM reads quantization from the checkpoint's
configuration. Remote model code is not trusted by default. Downloads are
disabled; acquire missing artifacts separately using the Hugging Face tools.
Do not download a second copy just for this container.

## Resource usage and troubleshooting

The 0.50 GPU memory utilization default reserves roughly half of GPU-visible
memory for this instance, leaving room for llama.cpp and other workloads. It is
not a global reservation or coordination mechanism: tune both services to the
actual free unified memory. Increase the budget only if needed for your model.

First startup can take minutes for weight loading and kernel compilation. Health
checks allow 15 minutes before counting startup failures. Logs report the chosen
snapshot; `/health` becomes ready after vLLM initializes. Test an actual inference
request to verify the model, quantization and kernels together.

If no candidates appear, check for complete Safetensors shards, a root model
`config.json`, tokenizer files, broken symlinks and UID 10001 read permissions.
A downloaded GGUF repository alone is not a vLLM candidate. If multiple candidates
appear, select a repository/revision with `VLLM_MODEL`.

For unsupported-model/kernel errors, check upstream model support and GB10
compatibility for the pinned version. An NVFP4 label alone does not guarantee
kernel support. For memory failures, reduce context/concurrency or stop other GPU
workloads. No models are loaded by a second vLLM process automatically.

The filesystem is read-only except `/tmp` and private shared memory. `/tmp` is
explicitly executable because Triton/FlashInfer load JIT-compiled shared libraries. HF files stay
on their host bind mount. JIT caches are temporary (up to 8 GiB in `/tmp`) and are
lost when the container is recreated. Shared memory is limited to 2 GiB; host IPC
and privileged mode are not used. Logs go to normal Docker logging.

## Upgrade, shutdown and removal

Update `VLLM_IMAGE` to a tested pinned ARM64 tag in `.env`, then:

```bash
./compose.sh vllm build --pull
./compose.sh vllm up -d --force-recreate
./compose.sh vllm down
```

`down` stops inference and removes the project containers/network without deleting
shared HF models. Clear `VLLM_API_BASE` and recreate LiteLLM to remove the route.
Remove unused images separately if desired. The host cache is never deleted.

Local launcher tests: `python3 -m unittest discover -s vllm -p 'test_*.py'`.
