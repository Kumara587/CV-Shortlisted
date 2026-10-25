FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
ENV VITE_API_BASE_URL=""
RUN npm run build

FROM caddy:2-alpine AS gateway
COPY --from=frontend /build/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile

FROM python:3.12-slim AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SCREENER_DATA_DIR=/data
WORKDIR /app
COPY backend/requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt && groupadd -g 10001 screener && useradd -u 10001 -g screener -s /usr/sbin/nologin screener && mkdir /data && chown screener:screener /data && chmod 700 /data
COPY backend/*.py ./
COPY deploy/logging.json /app/logging.json
USER 10001:10001
EXPOSE 8000
CMD ["python","-m","uvicorn","main:app","--host","0.0.0.0","--port","8000","--workers","1","--proxy-headers","--forwarded-allow-ips","172.30.0.2","--no-access-log","--log-config","/app/logging.json"]
