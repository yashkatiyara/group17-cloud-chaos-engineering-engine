FROM python:3.11-slim

# Install system networking and diagnostics tools needed for chaos experimentation
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    iptables \
    curl \
    procps \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway.py order_service.py inventory_service.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["./entrypoint.sh"]
