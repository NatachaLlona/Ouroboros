FROM node:24.15.0-bookworm-slim AS build
WORKDIR /source
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm --prefix frontend ci --no-fund --no-audit
COPY app/text_limits.json ./app/text_limits.json
COPY frontend ./frontend
RUN npm --prefix frontend run build

FROM nginx:1.28-alpine
ENV OUROBOROS_API_UPSTREAM=api:8000
RUN apk add --no-cache nodejs
COPY --from=build /source/frontend/dist/browser /usr/share/nginx/html/frontend
COPY frontend/scripts/generate-assistant-theme.mjs /opt/generate-assistant-theme.mjs
COPY modules/frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY modules/frontend/entrypoint.sh /docker-entrypoint.d/40-public-config.sh
RUN chmod +x /docker-entrypoint.d/40-public-config.sh
