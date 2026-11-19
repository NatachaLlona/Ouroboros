FROM python:3.12-slim-bookworm
ENV PYTHONPATH=/runtime/modules:/runtime PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /runtime
COPY modules/api/requirements.txt modules/api/requirements.txt
RUN pip install --no-cache-dir -r modules/api/requirements.txt
COPY modules/api/service modules/api/service
COPY modules/api/app/login_throttle.py modules/api/app/login_throttle.py
COPY modules/api/config.example.jsonc modules/api/config.example.jsonc
COPY modules/database/__init__.py modules/database/settings.py modules/database/model.py modules/database/provision.py modules/database/
COPY modules/database/sql/api_migrations modules/database/sql/api_migrations
COPY shared shared
CMD ["python", "-m", "api.service.runtime"]
