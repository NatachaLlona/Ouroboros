FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /runtime
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY api ./api
COPY shared ./shared
COPY database/sql ./database/sql
COPY database/config.example.json ./database/config.example.json
COPY assistance/config.example.json ./assistance/config.example.json
CMD ["python", "-m", "api.runtime"]
