# Build từ gốc repo: docker build -f services/briefing/Dockerfile .
# Service BẢN TIN: CHỈ ĐỌC dữ liệu (DB role ts_ro); ghi DUY NHẤT bảng briefings bằng role ts_briefing + phát stream briefing.items / alerts.out.
# KHÔNG chạy LLM trong container này: gọi llama.cpp server (service briefing-llm, mạng nội bộ). Không có công cụ/hành động/đường đặt lệnh.
FROM python:3.12-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/briefing /app/services/briefing
RUN pip install --no-cache-dir /app/libs/common /app/services/briefing \
 && useradd -r -u 10001 app
ENV PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "briefing.main"]
