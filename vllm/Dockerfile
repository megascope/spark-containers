ARG VLLM_IMAGE=vllm/vllm-openai:v0.28.0
FROM ${VLLM_IMAGE}

# Use the upstream ARM64/CUDA stack; no replacement Torch or CUDA packages.
USER root
RUN mkdir -p /app /hf-cache /home/vllm \
 && chown 10001:10001 /home/vllm
COPY start.py /app/start.py
USER 10001:10001
WORKDIR /home/vllm
ENTRYPOINT ["python3", "/app/start.py"]
