# Build từ gốc repo: docker build -f services/journal/Dockerfile .
# Service CHỈ ĐỌC dữ liệu giao dịch (DB role ts_ro); ghi DUY NHẤT bảng journal_notes bằng role ts_journal. Không có đường đặt lệnh.
FROM python:3.12-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/journal /app/services/journal
RUN pip install --no-cache-dir /app/libs/common /app/services/journal \
 && useradd -r -u 10001 app
ENV PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "journal.main"]
