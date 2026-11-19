FROM python:3.12-slim-bookworm
ENV PYTHONPATH=/runtime/modules:/runtime PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /runtime
COPY modules/api/requirements.txt ./modules/api/requirements.txt
RUN pip install --no-cache-dir -r modules/api/requirements.txt
COPY modules/api ./modules/api
COPY shared ./shared
COPY modules/database/sql ./modules/database/sql
COPY qa/support/legacy ./qa/support/legacy
COPY modules/assistance/config.example.json ./modules/assistance/config.example.json
CMD ["python", "-m", "api.runtime"]
