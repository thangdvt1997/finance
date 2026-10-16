# Build từ gốc repo: docker build -f services/paper-trader/Dockerfile .
# MÔ PHỎNG: image không chứa SDK broker nào. Base ghim digest; lock có hash: services/paper-trader/requirements.lock (infra/ops/lock_deps.sh paper-trader) (peewee của empyrical chỉ có sdist nên không ép --only-binary).
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY services/paper-trader/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY libs/common /app/libs/common
COPY services/paper-trader /app/services/paper-trader
RUN pip install --no-cache-dir --no-deps /app/libs/common /app/services/paper-trader \
 && useradd -r -u 10001 app
ENV PORT=8000 PAPER_CONFIG=/app/services/paper-trader/paper.example.yaml PAPER_STRATEGY_DIR=/app/services/paper-trader/strategies
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "paper_trader.main"]
