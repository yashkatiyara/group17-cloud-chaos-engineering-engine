#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon is not reachable. Start Docker Desktop/systemd Docker and retry."
    echo "       The control plane needs the Docker socket to inject and roll back faults."
    exit 1
fi

echo "=========================================================="
echo "⚡ Group 17: Cloud Chaos Engineering Engine (Mini-Project)"
echo "=========================================================="
echo "[1/3] Building and starting Docker containers..."
docker compose up --build -d

echo "[2/3] Waiting for target services to become healthy..."
MAX_RETRIES=20
COUNT=0
while [ $COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8088/health | grep -q '"overall_system_healthy":true'; then
        echo " -> API Gateway and Microservices are ONLINE and HEALTHY!"
        break
    fi
    echo " -> Waiting for services to boot... ($COUNT/$MAX_RETRIES)"
    sleep 1.5
    COUNT=$((COUNT + 1))
done

if ! curl -fsS http://localhost:8088/health >/dev/null 2>&1; then
    echo "ERROR: Target services did not become healthy within ${MAX_RETRIES} checks."
    docker compose ps
    docker compose logs --tail=80 gateway order-service inventory-service chaos-engine
    exit 1
fi

echo "[3/3] Checking Chaos Engine Control Plane..."
sleep 2
if curl -fsS http://localhost:9000/healthz | grep -q '"status":"healthy"'; then
    echo " -> Chaos Control Plane is ONLINE!"
else
    echo "ERROR: Chaos Control Plane did not become healthy."
    docker compose ps
    docker compose logs --tail=80 chaos-engine
    exit 1
fi

echo ""
echo "=========================================================="
echo "🚀 SYSTEM READY!"
echo "=========================================================="
echo " 🌐 Web Dashboard:         http://localhost:9000"
echo " 🛡️ Target API Gateway:    http://localhost:8088"
echo " 🩺 Health Check:          http://localhost:8088/health"
echo " 📊 Metrics Endpoint:      http://localhost:8088/metrics"
echo " 📦 Products Catalog:      http://localhost:8088/api/products"
echo "=========================================================="
echo " To run automated demo test: python3 test_demo.py"
echo " To view logs:               docker compose logs -f"
echo " To stop:                    ./stop.sh"
echo "=========================================================="
