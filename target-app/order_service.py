import time
import os
import uuid
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Order Service", version="1.0.0")

START_TIME = time.time()
REQUEST_COUNT = 0
ERROR_COUNT = 0

INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:5002")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "2.5"))

ORDERS = []

class OrderRequest(BaseModel):
    item_id: int
    quantity: int
    customer_email: str = "customer@example.com"

@app.middleware("http")
async def count_requests(request, call_next):
    global REQUEST_COUNT, ERROR_COUNT
    REQUEST_COUNT += 1
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            ERROR_COUNT += 1
        return response
    except Exception as e:
        ERROR_COUNT += 1
        raise e

@app.get("/health")
async def health_check():
    # Downstream dependency health check to verify microservice connectivity
    inventory_healthy = False
    inventory_latency_ms = None
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{INVENTORY_SERVICE_URL}/health")
            if resp.status_code == 200:
                inventory_healthy = True
            inventory_latency_ms = round((time.time() - t0) * 1000, 2)
    except Exception:
        inventory_healthy = False

    status = "healthy" if inventory_healthy else "degraded"
    return {
        "status": status,
        "service": "order-service",
        "hostname": os.getenv("HOSTNAME", "order-node"),
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "downstream_dependencies": {
            "inventory_service": {
                "healthy": inventory_healthy,
                "latency_ms": inventory_latency_ms
            }
        }
    }

@app.post("/orders")
async def create_order(payload: OrderRequest):
    order_id = str(uuid.uuid4())[:8]
    t0 = time.time()

    # Step 1: Call Inventory Service to reserve stock
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            reserve_resp = await client.post(
                f"{INVENTORY_SERVICE_URL}/reserve",
                json={"item_id": payload.item_id, "quantity": payload.quantity}
            )
            if reserve_resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Item not found in inventory")
            elif reserve_resp.status_code == 400:
                raise HTTPException(status_code=400, detail="Insufficient stock")
            elif reserve_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Inventory error: {reserve_resp.text}")
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"Downstream dependency timeout: Inventory Service did not respond within {REQUEST_TIMEOUT}s"
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Downstream dependency unavailable: Cannot connect to Inventory Service ({str(exc)})"
        )

    # Step 2: Confirm Order
    order_record = {
        "order_id": order_id,
        "item_id": payload.item_id,
        "quantity": payload.quantity,
        "customer_email": payload.customer_email,
        "status": "CONFIRMED",
        "created_at": time.time(),
        "processing_time_ms": round((time.time() - t0) * 1000, 2)
    }
    ORDERS.append(order_record)
    return order_record

@app.get("/orders")
def list_orders():
    return ORDERS[-50:]  # Return last 50 orders

@app.get("/metrics")
def get_metrics():
    return {
        "requests_total": REQUEST_COUNT,
        "errors_total": ERROR_COUNT,
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
