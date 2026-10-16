# Build từ GỐC repo:  docker build -f services/web-ui/Dockerfile .   (context = thư mục gốc, giống các service khác)
# Giai đoạn 1: build SPA (Vite) -> file tĩnh. Không cần node trên server, không CDN lúc chạy.
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /app
COPY services/web-ui/app/package.json services/web-ui/app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY services/web-ui/app/ ./
RUN npm run build

# Giai đoạn 2: nginx không đặc quyền (listen 8080), chỉ chứa file tĩnh + cấu hình.
FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3
USER root
RUN rm -f /etc/nginx/conf.d/default.conf && mkdir -p /etc/nginx/snippets /etc/nginx/auth && chown -R 101:101 /etc/nginx/auth
COPY services/web-ui/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY services/web-ui/nginx/cache-zones.conf /etc/nginx/snippets/cache-zones.conf
COPY services/web-ui/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=755 services/web-ui/nginx/10-check-auth.sh /docker-entrypoint.d/10-check-auth.sh
COPY --from=build /app/dist /usr/share/nginx/html
# Nén sẵn (gzip -9, giữ file gốc) cho gzip_static: nginx không tốn CPU nén lúc chạy.
RUN find /usr/share/nginx/html -type f \( -name "*.js" -o -name "*.css" -o -name "*.html" -o -name "*.svg" -o -name "*.json" -o -name "*.webmanifest" -o -name "*.txt" \) -size +256c -exec gzip -9 -k -f {} +
# Chỉ thay 2 biến này khi render template (tránh đụng $host, $uri của nginx)
ENV NGINX_ENVSUBST_FILTER="^(API_KEY|GATEWAY_UPSTREAM|AUTH_UPSTREAM|AUTH_TRUST_SECRET|AUTH_BASIC_FALLBACK|API_PROXY_CACHE)$" \
    API_PROXY_CACHE="on" \
    GATEWAY_UPSTREAM="http://api-gateway:8000" \
    AUTH_UPSTREAM="http://auth:8000" \
    AUTH_BASIC_FALLBACK="0"
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=4s --retries=3 --start-period=10s \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
