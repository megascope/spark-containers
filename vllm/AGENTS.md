# vLLM on Spark

Follow the repository AGENTS.md. Keep the native ARM64/CUDA upstream image pinned.
The launcher discovers local HF Safetensors snapshots, selects one model, and execs
upstream vLLM. Do not add a custom inference router or automatic multi-model GPU
allocation. Keep HF mounts read-only and runtime compilation caches writable.
