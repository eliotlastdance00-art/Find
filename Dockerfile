# syntax=docker/dockerfile:1.7

# ---------- build: resolve and install dependencies into a virtual environment ----------
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /src

# CPU-only PyTorch keeps the image small. For a GPU image use the CUDA index instead.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
COPY constraints.txt ./
RUN pip install --extra-index-url "$TORCH_INDEX" --constraint constraints.txt torch torchvision

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --extra-index-url "$TORCH_INDEX" --constraint constraints.txt .

# Download during build, not while serving. Pinned hash, resume and an upstream mirror.
RUN DFD_WEIGHTS_DIR=/opt/model-weights dfd models --download

# ---------- runtime ----------
FROM python:3.13-slim AS runtime
LABEL org.opencontainers.image.title="Deepfake Detektor" \
      org.opencontainers.image.description="Deepfake detection for images, video and audio" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DFD_DATA_DIR=/data \
    DFD_WEIGHTS_DIR=/app/weights \
    DFD_LOG_JSON=true \
    HOME=/tmp

RUN groupadd --system --gid 10001 dfd \
 && useradd --system --uid 10001 --gid dfd --no-create-home dfd \
 && mkdir -p /data /app/weights \
 && chown -R dfd:dfd /data

COPY --from=build /opt/venv /opt/venv
COPY weights /app/weights
COPY --from=build /opt/model-weights/synthetic /app/weights/synthetic

USER dfd
WORKDIR /app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

# One process on purpose: the job queue and the live-progress broker are in-process.
CMD ["dfd", "serve", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
