FROM node:24.15.0-bookworm-slim AS build
WORKDIR /source
COPY modules/frontend/package.json modules/frontend/package-lock.json ./modules/frontend/
RUN npm --prefix modules/frontend ci --no-fund --no-audit
COPY shared/text_limits.json ./shared/text_limits.json
COPY modules/frontend ./modules/frontend
RUN npm --prefix modules/frontend run build

FROM nginx:1.28-alpine
ENV OUROBOROS_API_UPSTREAM=api:8000
RUN apk add --no-cache nodejs
COPY --from=build /source/modules/frontend/dist/browser /usr/share/nginx/html/frontend
COPY modules/frontend/scripts/generate-assistant-theme.mjs /opt/generate-assistant-theme.mjs
COPY modules/frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY modules/frontend/entrypoint.sh /docker-entrypoint.d/40-public-config.sh
RUN chmod +x /docker-entrypoint.d/40-public-config.sh
