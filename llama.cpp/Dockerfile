FROM nvidia/cuda:13.0.2-devel-ubuntu24.04 AS build

RUN apt-get update && apt-get install -y \
    git \
    cmake \
    build-essential \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 https://github.com/ggml-org/llama.cpp /src/llama.cpp

WORKDIR /src/llama.cpp

RUN cmake -B build \
      -DGGML_CUDA=ON \
      -DGGML_CURL=ON \
      -DCMAKE_CUDA_ARCHITECTURES=121a-real \
    && cmake --build build \
      --config Release \
      --target llama-server \
      -j"$(nproc)"


FROM nvidia/cuda:13.0.2-runtime-ubuntu24.04

ARG UID=10001
ARG GID=10001

RUN apt-get update && apt-get install -y \
      libcurl4 \
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
    && mkdir -p /models \
    && chown llama:llama /models

COPY --from=build \
  /src/llama.cpp/build/bin/llama-server \
  /usr/local/bin/llama-server

USER llama:llama

WORKDIR /home/llama

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/llama-server"]
