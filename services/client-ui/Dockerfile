# Ứng dụng CLIENT (PWA /c/). Build từ GỐC repo:  docker build -f services/client-ui/Dockerfile .
# Giai đoạn 1: build SPA (Vite) -> file tĩnh. Không cần node trên server, không CDN lúc chạy.
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /app
COPY services/client-ui/app/package.json services/client-ui/app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY services/client-ui/app/ ./
RUN npm run build

# Giai đoạn 2: nginx không đặc quyền (listen 8080); tệp tĩnh đặt dưới /c/.
FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3
USER root
RUN rm -f /etc/nginx/conf.d/default.conf && mkdir -p /etc/nginx/snippets /usr/share/nginx/html/c
COPY services/client-ui/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY services/client-ui/nginx/auth-proxy.conf /etc/nginx/snippets/auth-proxy.conf
COPY services/client-ui/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html/c
# Chỉ thay các biến này khi render template (tránh đụng $host, $uri của nginx)
ENV NGINX_ENVSUBST_FILTER="^(API_KEY|GATEWAY_UPSTREAM|AUTH_UPSTREAM|AUTH_TRUST_SECRET)$" \
    GATEWAY_UPSTREAM="http://api-gateway:8000" \
    AUTH_UPSTREAM="http://auth:8000"
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=4s --retries=3 --start-period=10s \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
