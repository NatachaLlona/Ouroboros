FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /runtime
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY modules/__init__.py modules/service_auth.py ./modules/
COPY modules/base ./modules/base
COPY sql ./sql
COPY .ai.config.example .app.config.example ./
CMD ["python", "-m", "modules.base.runtime"]
