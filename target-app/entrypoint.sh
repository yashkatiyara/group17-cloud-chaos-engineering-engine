#!/bin/bash
set -e

echo "[STARTUP] Starting service: ${SERVICE_NAME:-gateway}"

if [ "$SERVICE_NAME" = "gateway" ]; then
    exec python3 gateway.py
elif [ "$SERVICE_NAME" = "order-service" ]; then
    exec python3 order_service.py
elif [ "$SERVICE_NAME" = "inventory-service" ]; then
    exec python3 inventory_service.py
else
    echo "Unknown SERVICE_NAME: $SERVICE_NAME, defaulting to gateway"
    exec python3 gateway.py
fi
