FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ ./core/
COPY templates/ ./templates/
COPY static/ ./static/
COPY main.py .

ENV PYTHONUNBUFFERED=1

EXPOSE 9000

CMD ["python3", "main.py"]
