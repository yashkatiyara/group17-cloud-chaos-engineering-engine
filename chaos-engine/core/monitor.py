import time
import httpx
from collections import deque
from typing import Dict, Any, List

class HealthMonitor:
    def __init__(self, gateway_url: str = "http://gateway:8088"):
        self.gateway_url = gateway_url.rstrip("/")
        self.history = deque(maxlen=60)
        self.latest_status: Dict[str, Any] = {
            "gateway": "UNKNOWN",
            "order_service": "UNKNOWN",
            "inventory_service": "UNKNOWN",
            "overall_healthy": True,
            "latency_p95_ms": 0.0,
            "error_rate_pct": 0.0,
            "last_probe_timestamp": 0
        }

    async def probe_once(self) -> Dict[str, Any]:
        """Probes the target environment and computes instantaneous metrics."""
        t0 = time.time()
        success = False
        status_code = 0
        services_state = {}

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.gateway_url}/health")
                status_code = resp.status_code
                elapsed_ms = (time.time() - t0) * 1000.0

                if resp.status_code == 200:
                    data = resp.json()
                    services_state = data.get("services", {})
                    success = data.get("overall_system_healthy", True)
                elif resp.status_code in (502, 503, 504):
                    try:
                        data = resp.json()
                        services_state = data.get("services", {})
                    except Exception:
                        pass
                    success = False
                else:
                    success = False

        except httpx.TimeoutException:
            elapsed_ms = (time.time() - t0) * 1000.0
            status_code = 504
            success = False
        except Exception:
            elapsed_ms = (time.time() - t0) * 1000.0
            status_code = 503
            success = False

        probe_record = {
            "timestamp": time.time(),
            "status_code": status_code,
            "latency_ms": round(elapsed_ms, 2),
            "success": success
        }
        self.history.append(probe_record)

        # Calculate metrics over recent window
        recent = list(self.history)
        total = len(recent)
        failures = sum(1 for p in recent if not p["success"])
        error_rate = round((failures / total * 100), 2) if total > 0 else 0.0

        latencies = sorted([p["latency_ms"] for p in recent])
        if latencies:
            p50 = latencies[int(len(latencies) * 0.50)]
            p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)]
        else:
            p50 = p95 = 0.0

        # Parse individual service health
        order_status = "HEALTHY"
        inv_status = "HEALTHY"

        if "order_service" in services_state:
            s = services_state["order_service"].get("status", "")
            if s == "healthy":
                order_status = "HEALTHY"
            elif s == "degraded":
                order_status = "DEGRADED"
            else:
                order_status = "DOWN"
        elif not success:
            order_status = "UNKNOWN"

        if "inventory_service" in services_state:
            s = services_state["inventory_service"].get("status", "")
            if s == "healthy":
                inv_status = "HEALTHY"
            else:
                inv_status = "DOWN"
        elif not success:
            inv_status = "UNKNOWN"

        self.latest_status = {
            "gateway": "HEALTHY" if status_code in (200, 503) else "DOWN",
            "order_service": order_status,
            "inventory_service": inv_status,
            "overall_healthy": success,
            "last_status_code": status_code,
            "instant_latency_ms": round(elapsed_ms, 2),
            "latency_p50_ms": round(p50, 2),
            "latency_p95_ms": round(p95, 2),
            "error_rate_pct": error_rate,
            "total_probes_tracked": total,
            "last_probe_timestamp": time.time()
        }
        return self.latest_status

    def get_latest_status(self) -> Dict[str, Any]:
        return self.latest_status

    def get_recent_history(self) -> List[Dict[str, Any]]:
        return list(self.history)
