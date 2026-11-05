FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /runtime
COPY assistance/requirements.txt ./assistance/requirements.txt
RUN pip install --no-cache-dir -r assistance/requirements.txt
COPY assistance ./assistance
COPY shared ./shared
CMD ["python", "-m", "assistance.main"]
