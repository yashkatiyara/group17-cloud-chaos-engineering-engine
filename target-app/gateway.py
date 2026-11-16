import time
import os
import httpx
from collections import deque
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Cloud API Gateway & Reverse Proxy", version="1.0.0")

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:5001")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5002")

START_TIME = time.time()
REQUEST_LATENCIES = deque(maxlen=200)
STATUS_CODES = deque(maxlen=200)

class CheckoutRequest(BaseModel):
    item_id: int
    quantity: int
    customer_email: str = "user@cloudscale.io"

@app.middleware("http")
async def track_telemetry(request: Request, call_next):
    t0 = time.time()
    try:
        response: Response = await call_next(request)
        elapsed_ms = (time.time() - t0) * 1000.0
        REQUEST_LATENCIES.append(elapsed_ms)
        STATUS_CODES.append(response.status_code)
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"
        return response
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000.0
        REQUEST_LATENCIES.append(elapsed_ms)
        STATUS_CODES.append(500)
        raise e

@app.get("/")
def root():
    return {
        "service": "cloud-api-gateway",
        "description": "Public Ingress for Distributed E-Commerce Microservices",
        "endpoints": [
            "/health",
            "/metrics",
            "/api/products",
            "/api/checkout",
            "/api/orders"
        ]
    }

@app.get("/health")
async def aggregated_health():
    """Aggregated health check querying all downstream microservices."""
    results = {}
    is_healthy = True

    async with httpx.AsyncClient(timeout=1.5) as client:
        # Check Order Service
        try:
            r = await client.get(f"{ORDER_SERVICE_URL}/health")
            results["order_service"] = r.json() if r.status_code == 200 else {"status": "unhealthy", "code": r.status_code}
            if r.status_code != 200:
                is_healthy = False
        except Exception as exc:
            results["order_service"] = {"status": "unreachable", "error": str(exc)}
            is_healthy = False

        # Check Inventory Service
        try:
            r = await client.get(f"{INVENTORY_SERVICE_URL}/health")
            results["inventory_service"] = r.json() if r.status_code == 200 else {"status": "unhealthy", "code": r.status_code}
            if r.status_code != 200:
                is_healthy = False
        except Exception as exc:
            results["inventory_service"] = {"status": "unreachable", "error": str(exc)}
            is_healthy = False

    status_code = 200 if is_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "gateway_status": "healthy",
            "overall_system_healthy": is_healthy,
            "timestamp": time.time(),
            "uptime_seconds": round(time.time() - START_TIME, 2),
            "services": results
        }
    )

@app.get("/api/products")
async def get_products():
    """Proxies to inventory service to retrieve catalog."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            resp = await client.get(f"{INVENTORY_SERVICE_URL}/items")
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Gateway Timeout: Inventory service did not respond")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Service Unavailable: {str(exc)}")

@app.post("/api/checkout")
async def checkout(payload: CheckoutRequest):
    """Executes order placement through order-service."""
    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            resp = await client.post(
                f"{ORDER_SERVICE_URL}/orders",
                json=payload.model_dump()
            )
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Gateway Timeout: Order service timed out during checkout")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Service Unavailable: Cannot connect to order-service ({str(exc)})")

@app.get("/api/orders")
async def get_orders():
    """Proxies to order service to list orders."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            resp = await client.get(f"{ORDER_SERVICE_URL}/orders")
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc))

@app.get("/metrics")
def get_telemetry():
    """Real-time latency and error telemetry for the Steady-State Health Monitor."""
    latencies = list(REQUEST_LATENCIES)
    codes = list(STATUS_CODES)

    total_requests = len(codes)
    error_count = sum(1 for c in codes if c >= 500)
    error_rate_pct = round((error_count / total_requests * 100), 2) if total_requests > 0 else 0.0

    if latencies:
        sorted_lat = sorted(latencies)
        p50 = round(sorted_lat[int(len(sorted_lat) * 0.50)], 2)
        p95 = round(sorted_lat[min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)], 2)
        p99 = round(sorted_lat[min(int(len(sorted_lat) * 0.99), len(sorted_lat) - 1)], 2)
        avg = round(sum(sorted_lat) / len(sorted_lat), 2)
    else:
        p50 = p95 = p99 = avg = 0.0

    return {
        "total_requests_tracked": total_requests,
        "error_count": error_count,
        "error_rate_percent": error_rate_pct,
        "latency_ms": {
            "avg": avg,
            "p50": p50,
            "p95": p95,
            "p99": p99
        },
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
