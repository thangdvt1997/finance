# Build từ gốc repo: docker build -f services/auth/Dockerfile .
# Service đăng nhập master/client (docs/AUTH.md). DB role ts_auth (bảng portal_users/mt_accounts/user_accounts/portal_sessions + audit_log append-only).
FROM python:3.12-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/auth /app/services/auth
RUN pip install --no-cache-dir /app/libs/common /app/services/auth \
 && useradd -r -u 10001 app
ENV PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "-m", "auth.main"]
