FROM python:3.12-slim-bookworm
ENV PYTHONPATH=/runtime/modules:/runtime PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /runtime
COPY modules/assistance/requirements.txt ./modules/assistance/requirements.txt
RUN pip install --no-cache-dir -r modules/assistance/requirements.txt
COPY modules/assistance ./modules/assistance
COPY shared ./shared
CMD ["python", "-m", "assistance.main"]
