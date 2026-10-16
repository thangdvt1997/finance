# Build từ gốc repo: docker build -f services/ai-trading-worker/Dockerfile .
# Worker nền (backtest Kịch bản mới): numpy/pandas/pyarrow (lock có hash, chỉ wheel). Dùng lại backtest.py của pattern-research + schema/store của ai-trading.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/ai-trading-worker/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /app/requirements.lock
COPY services/ai-trading /app/services/ai-trading
COPY services/ai-trading-worker /app/services/ai-trading-worker
COPY services/pattern-research/pattern_research/__init__.py services/pattern-research/pattern_research/backtest.py /app/pattern_research/
RUN pip install --no-cache-dir --no-deps /app/services/ai-trading /app/services/ai-trading-worker \
 && useradd -r -u 10001 app
ENV PYTHONPATH=/app AI_STATE_DIR=/state PATTERN_DATA=/data/patterns OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONUNBUFFERED=1
USER app
HEALTHCHECK --interval=30s CMD python -c "import time,sys;sys.exit(0 if time.time()-int(open('/state/worker.heartbeat').read())<90 else 1)"
CMD ["python", "-m", "ai_trading_worker.main"]
