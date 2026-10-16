# Build context = thư mục gốc repo:  docker build -f services/nlp/Dockerfile .
# Image gọn: KHÔNG có torch/transformers (ONNX Runtime + tokenizers). Model nằm ở volume /models (tải lần đầu từ HF).
# Base ghim digest (Renovate); lock có hash: services/nlp/requirements.lock (infra/ops/lock_deps.sh nlp), chỉ nhận wheel.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY services/nlp/requirements.lock /src/requirements.lock
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --only-binary=:all: --require-hashes -r /src/requirements.lock
COPY libs/common /src/libs/common
COPY services/nlp /src/services/nlp
RUN /opt/venv/bin/pip install --no-deps /src/libs/common /src/services/nlp \
 && find /opt/venv -name '__pycache__' -type d -prune -exec rm -rf {} + \
 && rm -rf /opt/venv/lib/python3.12/site-packages/pip /opt/venv/lib/python3.12/site-packages/setuptools* /src/services/nlp/build

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH OMP_NUM_THREADS=3 TOKENIZERS_PARALLELISM=false \
    NLP_MODEL_DIR=/models NLP_CONFIG_DIR=/app/config SERVICE_NAME=nlp PORT=8000
RUN useradd -u 10001 -m nlp && mkdir /models && chown nlp /models
COPY --from=build /opt/venv /opt/venv
COPY services/nlp/config /app/config
USER nlp
VOLUME /models
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request as u;u.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
CMD ["python", "-m", "nlp"]
