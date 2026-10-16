# Ảnh dev tạm chạy test trên VPS (chỉ thư viện; mã được mount). Không dùng cho production.
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest pytest-asyncio pyyaml pydantic redis fakeredis fastapi httpx uvicorn prometheus-client asyncpg
