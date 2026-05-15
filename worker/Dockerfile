FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY worker/requirements.txt /tmp/worker-requirements.txt

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
  && pip install --no-cache-dir -r /tmp/worker-requirements.txt \
  && rm -rf /var/lib/apt/lists/*

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "worker.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
