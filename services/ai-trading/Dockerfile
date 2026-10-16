# Build từ gốc repo: docker build -f services/ai-trading/Dockerfile .
# Lock có hash: services/ai-trading/requirements.lock (cùng bộ với alert-service: fastapi/redis/pyyaml/uvicorn/prometheus).
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/ai-trading/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/ai-trading /app/services/ai-trading
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/ai-trading \
 && useradd -r -u 10001 app
# registry + hiện vật backtest được compose mount :ro đè lên các đường dẫn này (thêm kịch bản = sửa YAML, không build lại)
ENV PORT=8000 AI_REGISTRY_DIR=/app/services/ai-trading/registry AI_RESEARCH_DIR=/research/pattern_sell
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "ai_trading.main"]
