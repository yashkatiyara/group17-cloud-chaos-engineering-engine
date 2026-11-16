import time
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Inventory Service", version="1.0.0")

START_TIME = time.time()
REQUEST_COUNT = 0
ERROR_COUNT = 0

# In-memory inventory state
INVENTORY = {
    1: {"id": 1, "name": "Cloud Computing Textbook", "price": 49.99, "stock": 100},
    2: {"id": 2, "name": "Docker Swarm USB Dongle", "price": 19.99, "stock": 50},
    3: {"id": 3, "name": "Chaos Monkey Plush Toy", "price": 24.99, "stock": 80},
    4: {"id": 4, "name": "Enterprise NVMe SSD 2TB", "price": 189.99, "stock": 30},
}

class ReserveRequest(BaseModel):
    item_id: int
    quantity: int

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
def health_check():
    return {
        "status": "healthy",
        "service": "inventory-service",
        "hostname": os.getenv("HOSTNAME", "inventory-node"),
        "uptime_seconds": round(time.time() - START_TIME, 2),
    }

@app.get("/items")
def list_items():
    return list(INVENTORY.values())

@app.post("/reserve")
def reserve_stock(payload: ReserveRequest):
    item = INVENTORY.get(payload.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item["stock"] < payload.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")
    item["stock"] -= payload.quantity
    return {
        "status": "reserved",
        "item_id": payload.item_id,
        "remaining_stock": item["stock"]
    }

@app.get("/metrics")
def get_metrics():
    return {
        "requests_total": REQUEST_COUNT,
        "errors_total": ERROR_COUNT,
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)
