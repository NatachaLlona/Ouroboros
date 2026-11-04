FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /runtime
COPY requirements-transcription.txt ./
COPY modules/assistance/requirements.txt ./modules/assistance/requirements.txt
RUN pip install --no-cache-dir -r modules/assistance/requirements.txt
COPY app/config.py app/ai_config.py app/transcription.py app/form_assistant.py app/errors.py app/audit_context.py app/request_context.py app/log_safety.py app/audit_privacy.py app/datetimes.py app/pagination.py app/text_limits.py app/text_limits.json app/error_codes.json ./app/
COPY app/schemas ./app/schemas
COPY .ai.config.example ./
COPY modules/__init__.py modules/service_auth.py ./modules/
COPY modules/assistance ./modules/assistance
CMD ["python", "-m", "modules.assistance.main"]
