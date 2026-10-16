# Build từ gốc repo: docker build -f services/track-record/Dockerfile .
# Đọc dữ liệu bằng role ts_ro; ghi DUY NHẤT bảng tr_* bằng ts_trackrec và Redis key `tr:*`. Không có đường đặt lệnh, không sinh văn bản tự do.
FROM python:3.12-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/track-record /app/services/track-record
RUN pip install --no-cache-dir /app/libs/common /app/services/track-record \
 && useradd -r -u 10001 app
ENV PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "track_record.main"]
