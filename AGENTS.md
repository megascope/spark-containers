# AGENTS.md — NVIDIA DGX Spark Projects

## Purpose

This repository contains projects intended to run on an NVIDIA DGX Spark.

The Spark is primarily a **GPU compute appliance**, not the user's general-purpose infrastructure server. Projects should take advantage of the Spark's GPU, unified memory, and NVIDIA software stack where useful, while avoiding unnecessary duplication of ordinary infrastructure that can run elsewhere.

Current and likely workloads include:

- ComfyUI and image generation
- Local LLM inference
- Prompt enhancement / rewriting models
- Vision and multimodal inference
- GPU-backed services for applications running elsewhere
- Immich / photo AI acceleration
- Experimental CUDA and ML workloads

Prefer small, understandable, self-contained services over large all-in-one stacks.

---

# Hardware

Target platform:

- NVIDIA DGX Spark
- ARM64 / `aarch64`
- NVIDIA GB10 Grace Blackwell platform
- Approximately 128 GB unified CPU/GPU memory
- CUDA-capable NVIDIA GPU
- Ubuntu / NVIDIA DGX software stack

Do **not** assume x86-64.

Always verify that:

- container images support `linux/arm64`
- Python wheels support ARM64
- CUDA libraries support the installed Spark software stack
- native dependencies compile correctly on ARM64

Avoid solutions that quietly depend on x86 emulation.

The large unified memory pool is one of the primary reasons for using this machine. It is acceptable to run models that would normally be impractical on consumer GPUs.

---

# Host Philosophy

Treat the Spark as a mostly headless compute server.

The desktop environment does not need to run during normal headless operation.

Prefer:

- containers for applications
- bind-mounted persistent data
- declarative configuration
- environment variables for site-specific paths/settings
- reproducible builds
- services that can be rebuilt without losing state

Avoid modifying the host unnecessarily.

GPU infrastructure and NVIDIA host components are exceptions and should normally remain host-managed.

---

# Containers

Docker / Docker Compose are the normal deployment mechanism for Spark projects.

Do not assume Docker `userns-remap` is enabled. It was investigated but deliberately deferred because of the complexity it introduces for bind-mounted model/data directories.

When creating a project, normally provide:

```text
project/
├── AGENTS.md
├── README.md
├── compose.yaml
├── .env.example
├── .gitignore
├── Dockerfile
└── ...
```

Use Compose rather than long `docker run` commands for persistent services.

Prefer explicit volume/bind declarations and explicit port mappings.

Do not expose services to every interface unless there is a reason to.

Prefer bindings such as:

```yaml
ports:
  - "127.0.0.1:8188:8188"
```

when a service only needs local access or will be reached through another proxy/tunnel.

If LAN access is required, make the bind address configurable.

---

# Configuration

Site-specific values belong in `.env`.

Always provide `.env.example`.

Useful conventions include:

```dotenv
DATA_DIR=/path/to/data
MODELS_DIR=/path/to/models
LISTEN_ADDR=127.0.0.1
```

Model-specific settings should also be configurable rather than baked into images.

For example:

```dotenv
MODEL=
MMPROJ=
```

Never commit:

- passwords
- API keys
- private keys
- WireGuard keys
- authentication tokens
- `.env`
- downloaded models

---

# Persistent Data

Large models and generated data should generally live outside container writable layers.

Use bind mounts for things such as:

```text
models/
input/
output/
user/
data/
```

Container rebuilds must not destroy user data or downloaded models.

Avoid copying multi-gigabyte model files into container images.

Model directories may be very large, so avoid unnecessary duplication.

---

# GPU / CUDA

Use NVIDIA's native CUDA stack.

When diagnosing GPU problems, distinguish carefully between:

1. host NVIDIA driver/runtime
2. NVIDIA container runtime/toolkit
3. CUDA libraries inside the container
4. application CUDA dependencies
5. architecture compatibility
6. model compatibility

Do not blindly install another NVIDIA driver inside an application container.

A common class of build failure is a linker expecting:

```text
libcuda.so.1
```

during compilation even though CUDA execution will ultimately occur through the host.

Understand whether a dependency needs:

- CUDA runtime libraries
- CUDA development libraries
- the driver API
- a linker stub
- the actual host driver library

before modifying the image.

Do not paper over CUDA linker problems by copying arbitrary host libraries into images.

---


# Hugging Face Models

Hugging Face repositories frequently contain far more files than are necessary for inference.

Do not automatically clone/download an entire repository.

Determine which artifacts are actually needed.

Possible formats include:

- safetensors
- GGUF
- tokenizer files
- configuration files
- multimodal projection files (`mmproj`)
- Hugging Face cache snapshots

For GGUF-based servers, prefer mounting the actual GGUF artifacts directly rather than requiring a complete Hugging Face cache unless the serving software specifically needs it.

---

# GGUF

GGUF inference is an important workload.

Projects may use llama.cpp-compatible servers or Ollama depending on the environment.

A model deployment should make these configurable:

```dotenv
MODEL=/models/model.gguf
MMPROJ=
```

`MMPROJ` is optional and should only be supplied for models requiring a multimodal projection model.

Do not assume every GGUF requires an `mmproj`.

For multimodal models, ensure that the GGUF and projection file are compatible versions.

When a model fails to load, check at least:

```bash
ls -l
stat
file
```

and validate:

- container-visible path
- permissions
- UID/GID
- architecture
- GGUF compatibility
- available memory
- command-line arguments

Do not immediately attribute model-loading failures to permissions.

---

# llama.cpp

llama.cpp-based servers are useful when direct GGUF control is desirable.

Prefer an OpenAI-compatible HTTP endpoint when practical so other software can use the service without custom integrations.

Expose configuration such as:

- model
- mmproj
- context size
- GPU layers / offload settings
- listen address
- port

through Compose/environment configuration.

Because this is a DGX Spark, optimize for CUDA rather than CPU inference.

---

# Ollama

Ollama is also used elsewhere, particularly on macOS.

GGUF models can be imported into Ollama with a `Modelfile`.

Do not require Ollama merely because a model is GGUF; use it when its model management/API ergonomics are useful.

Conversely, do not build a custom inference server when Ollama already provides everything required.

The user sometimes serves Ollama from another machine through SSH tunnels, so consumers should ideally support configurable base URLs.

---

# Network Architecture

The Spark is part of a larger homelab.

Do not assume every application that consumes Spark GPU services runs on the Spark itself.

A common architecture is:

```text
Application host
      │
      │ HTTP/API
      ▼
DGX Spark GPU service
      │
      ▼
GPU inference
```

Services should therefore expose clean APIs where practical.

Avoid tightly coupling GPU inference to the frontend application.

---

# Security

Assume the Spark may hold expensive models and potentially private data.

Default to least exposure.

Prefer:

```text
localhost
private LAN
WireGuard
Tailscale
```

over public listeners.

Do not create unauthenticated public inference endpoints.

Secrets belong in:

- `.env`
- Docker secrets where appropriate
- host-managed secret files
- external secret stores

not source control.

---

# Filesystem Encryption

Assume the Spark already has disk encryption.

Do not make design assumptions that require unattended access to encrypted disks before the machine has been unlocked unless that requirement is explicitly addressed.

Encryption performance can matter on this ARM platform, especially for high-throughput workloads.

Avoid unnecessary layers of encryption or filesystem abstraction in GPU data paths without measuring their cost.

---

# Resource Usage

The Spark consumes meaningful power even when idle.

Do not create needless always-running GPU processes.

Where reasonable:

- allow services to unload models
- avoid duplicate copies of models in memory
- make expensive background workers optional
- avoid polling at very high frequency
- allow projects to be stopped cleanly with Compose

However, don't sacrifice useful model caching merely to minimize memory use: the machine has a large unified memory pool specifically for compute workloads.

---

# Project Design Principles

When implementing a new Spark project:

1. Determine whether the workload genuinely benefits from the Spark GPU.
2. Check ARM64 support.
3. Check CUDA/Blackwell support.
4. Prefer an existing upstream project when it already solves the problem.
5. Containerize the service.
6. Keep persistent state outside the container.
7. Put local paths/settings in `.env`.
8. Provide `.env.example`.
9. Bind services narrowly by default.
10. Document model acquisition separately from container builds.
11. Avoid downloading duplicate model artifacts.
12. Provide health checks where practical.
13. Make logs available through normal container tooling.
14. Make upgrades/rebuilds reproducible.
15. Document how to completely remove the service without removing shared model/data directories.

---

# Before Adding Dependencies

Before adding an ML library, determine:

- Does it support ARM64?
- Does it support the installed Python version?
- Does it provide a compatible CUDA wheel?
- Does it support Blackwell?
- Does it compile cleanly on the Spark?
- Does NVIDIA provide an optimized version/container?
- Is there a Spark-specific fork or documented setup?

Search upstream issues/documentation when compatibility is unclear.

Do not assume instructions written for RTX x86 Linux systems apply unchanged to DGX Spark.

---

# Build Strategy

Keep Dockerfiles understandable.

Prefer pinned or bounded versions for important ML dependencies.

Avoid giant `RUN` commands when separating stages makes debugging easier.

Use build stages where they substantially reduce final image size or isolate compilers/development packages.

Clean package caches.

Example:

```dockerfile
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      git \
      curl \
 && rm -rf /var/lib/apt/lists/*
```

Do not optimize Dockerfile aesthetics at the expense of debuggability.

---

# Observability

Every long-running service should make it easy to determine:

- whether it is running
- whether CUDA was detected
- what model was loaded
- which port it is listening on
- whether an inference request succeeded

Where appropriate, add a Compose health check.

Logs should identify model-loading failures clearly.

Do not swallow stderr from inference engines.

---

# Performance Testing

When comparing implementations, measure rather than assume.

Useful metrics include:

- model load time
- peak unified-memory usage
- generation latency
- tokens/sec
- image generation time
- GPU utilization
- CPU utilization
- idle power
- active power

Record:

- model
- quantization
- resolution/context
- steps
- software version

when publishing benchmark results.

A benchmark without its model/precision/settings is not useful.

---

# Existing Performance Context

The Spark has shown very strong image-generation performance, particularly with NVFP4 models.

Observed qualitatively:

- substantially faster than a Radeon 7900 XT for suitable NVFP4 image-generation workflows
- only somewhat slower than some comparable workflows on an RTX 5070 Ti

Treat these as informal observations, not formal benchmarks.

Do not encode performance assumptions from them into software.

---

# Administrative Scripts

Small operational utilities are welcome.

Prefer Python for anything involving:

- JSON workflow parsing
- model inventories
- Hugging Face metadata
- structured output
- dependency graphs

Prefer shell for simple service/system operations.

CLI tools should generally:

- support `--help`
- return useful exit statuses
- fail clearly
- avoid destructive defaults
- support dry-run/report-only modes for destructive operations

---

# README Requirements

Every project should explain:

1. What it does.
2. Why it belongs on the Spark.
3. Architecture.
4. Prerequisites.
5. Installation.
6. Configuration.
7. Model acquisition, if applicable.
8. Startup/shutdown.
9. Upgrade procedure.
10. Troubleshooting.
11. Persistent directories.
12. Network exposure.
13. How to uninstall it without deleting user data.

Commands should be copy/pasteable.

---

# Working Style for Agents

When asked to implement something:

- Inspect the existing repository first.
- Preserve working infrastructure unless there is a concrete reason to change it.
- Make incremental changes.
- Explain consequential architecture decisions.
- Prefer straightforward solutions over elaborate frameworks.
- Do not introduce Kubernetes or other orchestration unless explicitly requested.
- Do not move ordinary infrastructure onto the Spark merely because it is available.
- Do not replace an existing working tool with a custom implementation without identifying the advantage.
- Search upstream documentation/issues when dealing with fast-moving Spark/CUDA compatibility questions.

If something depends on a fact that can be checked from the machine, prefer checking it rather than guessing.

Examples:

```bash
uname -m
nvidia-smi
docker version
docker compose version
ip addr
lsblk
df -h
```

Ask before making destructive changes.

---

# Overall Goal

Use the DGX Spark as a flexible, reproducible **GPU appliance for the homelab**.

The ideal project:

```text
normal infrastructure
        │
        │ clean API
        ▼
┌──────────────────────┐
│      DGX Spark       │
│                      │
│ containerized GPU    │
│ workload             │
│        │             │
│ shared model store   │
└──────────────────────┘
```

Keep the Spark powerful, simple, secure, and easy to experiment with.
