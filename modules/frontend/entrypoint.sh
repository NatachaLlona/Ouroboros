#!/bin/sh
set -eu
node /opt/generate-assistant-theme.mjs /config/frontend/config.json /usr/share/nginx/html/frontend/assistant-theme.css
cp /config/frontend/config.json /usr/share/nginx/html/frontend/runtime-config.json
