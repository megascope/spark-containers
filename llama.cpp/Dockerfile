FROM nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu22.04 AS build

ARG LLAMA_CPP_REF=v0.3.0

RUN apt-get update && apt-get install -y \
    git \
    cmake \
    build-essential \
    libcurl4-openssl-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 --branch "${LLAMA_CPP_REF}" \
      https://github.com/ggml-org/llama.cpp /src/llama.cpp

WORKDIR /src/llama.cpp

RUN cmake -B build \
      -DGGML_NATIVE=OFF \
      -DGGML_CUDA=ON \
      -DGGML_CURL=ON \
      -DGGML_BACKEND_DL=ON \
      -DGGML_CUDA_ENABLE_UNIFIED_MEMORY=1 \
      -DLLAMA_BUILD_TESTS=OFF \
      -DCMAKE_CUDA_ARCHITECTURES=121 \
      -DCMAKE_EXE_LINKER_FLAGS="-Wl,--allow-shlib-undefined" \
    && cmake --build build \
      --config Release \
      --target llama-server \
      -j"$(nproc)"

RUN mkdir -p /out/lib \
    && find build -name '*.so*' -exec cp -P {} /out/lib/ \; \
    && cp build/bin/llama-server /out/


FROM nvcr.io/nvidia/cuda:13.0.1-runtime-ubuntu22.04

ARG UID=10001
ARG GID=10001

RUN apt-get update && apt-get install -y \
      libcurl4 \
      libgomp1 \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${GID}" llama \
    && useradd \
         --uid "${UID}" \
         --gid "${GID}" \
         --create-home \
         --home-dir /home/llama \
         --shell /usr/sbin/nologin \
         llama \
    && mkdir -p /models /app \
    && chown llama:llama /models /app

COPY --from=build /out/lib/ /app/
COPY --from=build /out/llama-server /app/llama-server
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

RUN chmod 0555 /app/docker-entrypoint.sh

ENV LD_LIBRARY_PATH=/app:${LD_LIBRARY_PATH}

USER llama:llama

WORKDIR /home/llama

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
