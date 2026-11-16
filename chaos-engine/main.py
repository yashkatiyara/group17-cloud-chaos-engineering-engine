import os
import time
import asyncio
from typing import Dict, Any, List
from contextlib import asynccontextmanager
from collections import deque
from fastapi import Depends, FastAPI, HTTPException, Request, BackgroundTasks, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.scheduler import ExperimentScheduler, ExperimentDefinition
from core.injector import FaultInjector
from core.monitor import HealthMonitor
from core.circuit_breaker import CircuitBreaker

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTS_DIR = os.getenv("EXPERIMENTS_DIR", os.path.join(BASE_DIR, "..", "experiments"))
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8088")
DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "local-docker")
CLOUD_PROVIDER = os.getenv("CLOUD_PROVIDER", "docker")
CHAOS_API_TOKEN = os.getenv("CHAOS_API_TOKEN", "").strip()

# Core Engine Components
scheduler = ExperimentScheduler(experiments_dir=EXPERIMENTS_DIR)
injector = FaultInjector()
monitor = HealthMonitor(gateway_url=GATEWAY_URL)
circuit_breaker = CircuitBreaker(injector=injector)

# State
ACTIVE_EXPERIMENT: Dict[str, Any] = None
EVENT_LOGS = deque(maxlen=200)

def log_event(level: str, message: str, details: Any = None):
    entry = {
        "timestamp": time.time(),
        "time_str": time.strftime("%H:%M:%S", time.localtime()),
        "level": level,
        "message": message,
        "details": details
    }
    EVENT_LOGS.append(entry)
    print(f"[{entry['time_str']}][{level}] {message}")


def require_control_token(x_chaos_token: str = Header(default="")):
    """Protect state-changing chaos actions when the dashboard is cloud exposed."""
    if CHAOS_API_TOKEN and x_chaos_token != CHAOS_API_TOKEN:
        raise HTTPException(status_code=401, detail="Valid X-Chaos-Token header required")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure clean state and launch background prober
    log_event("INFO", "Chaos Control Plane initializing...")
    injector.rollback_all()
    log_event("SUCCESS", "System baseline verified. Control plane active.")
    
    # Launch background polling tasks
    telemetry_task = asyncio.create_task(background_telemetry_loop())
    traffic_task = asyncio.create_task(background_traffic_generator())
    
    yield
    
    # Shutdown
    log_event("WARN", "Shutting down Chaos Control Plane. Reverting all faults.")
    telemetry_task.cancel()
    traffic_task.cancel()
    injector.rollback_all()

app = FastAPI(title="Cloud Chaos Engineering Engine", version="1.0.0", lifespan=lifespan)

# Setup Templates & Static
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
static_dir = os.path.join(BASE_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

async def background_telemetry_loop():
    """Continuous high-frequency health monitoring loop."""
    global ACTIVE_EXPERIMENT
    while True:
        try:
            status = await monitor.probe_once()
            
            # If an experiment is running, check circuit breaker
            if ACTIVE_EXPERIMENT and ACTIVE_EXPERIMENT.get("status") == "RUNNING":
                exp_def = scheduler.get_experiment(ACTIVE_EXPERIMENT["id"])
                if exp_def:
                    eval_result = circuit_breaker.evaluate(status, exp_def)
                    if eval_result.get("tripped"):
                        trip = eval_result.get("trip_event", {})
                        log_event(
                            "CRITICAL",
                            f"🚨 CIRCUIT BREAKER TRIPPED! Breach: {', '.join(trip.get('reasons', []))}",
                            trip
                        )
                        log_event(
                            "SUCCESS",
                            f"Emergency rollback executed in {trip.get('rollback_duration_ms')}ms. Target state restored."
                        )
                        ACTIVE_EXPERIMENT["status"] = "ABORTED_BY_CIRCUIT_BREAKER"
                        ACTIVE_EXPERIMENT["completed_at"] = time.time()
                        ACTIVE_EXPERIMENT["trip_event"] = trip
        except Exception as e:
            print(f"[TelemetryLoop Error]: {e}")
        await asyncio.sleep(1.0)

async def background_traffic_generator():
    """Generates continuous realistic user traffic against the target gateway."""
    import httpx
    while True:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                # Alternate between viewing products and placing orders
                await client.get(f"{GATEWAY_URL}/api/products")
                await asyncio.sleep(1.5)
                await client.post(
                    f"{GATEWAY_URL}/api/checkout",
                    json={"item_id": 1, "quantity": 1, "customer_email": "chaos_tester@cloud.edu"}
                )
        except Exception:
            pass
        await asyncio.sleep(1.5)

async def run_experiment_worker(exp_def: ExperimentDefinition):
    """Executes the chaos experiment lifecycle."""
    global ACTIVE_EXPERIMENT
    log_event("INFO", f"Starting experiment '{exp_def.name}' (ID: {exp_def.id}) on target '{exp_def.target}'")
    
    # 1. Start circuit breaker monitoring
    circuit_breaker.start_monitoring()
    
    # 2. Inject fault
    try:
        inject_res = injector.inject_fault(
            target_name=exp_def.target,
            fault_type=exp_def.fault_type,
            params={
                "delay_ms": exp_def.delay_ms,
                "loss_percent": exp_def.loss_percent,
                "cpu_percent": exp_def.cpu_percent
            }
        )
        log_event(
            "WARN",
            f"Fault injected: {exp_def.fault_type} on '{exp_def.target}' (duration: {exp_def.duration_seconds}s)",
            inject_res
        )
    except Exception as e:
        log_event("ERROR", f"Failed to inject fault: {str(e)}")
        ACTIVE_EXPERIMENT["status"] = "FAILED"
        circuit_breaker.reset()
        return

    # 3. Observe for duration or until circuit breaker aborts
    start_time = time.time()
    while time.time() - start_time < exp_def.duration_seconds:
        if ACTIVE_EXPERIMENT.get("status") != "RUNNING":
            # Tripped or stopped early
            return
        await asyncio.sleep(1.0)

    # 4. If not tripped, normal completion and rollback
    if ACTIVE_EXPERIMENT.get("status") == "RUNNING":
        log_event("INFO", f"Experiment duration elapsed ({exp_def.duration_seconds}s). Initiating planned rollback...")
        rollback_res = injector.rollback_all()
        log_event("SUCCESS", "Planned rollback complete. Baseline restored.", rollback_res)
        ACTIVE_EXPERIMENT["status"] = "COMPLETED"
        ACTIVE_EXPERIMENT["completed_at"] = time.time()
        circuit_breaker.reset()

# ----------------- HTTP Routes -----------------

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Renders the interactive web dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "gateway_url": GATEWAY_URL,
            "experiments": scheduler.list_experiments()
        }
    )


@app.get("/healthz")
async def control_plane_health():
    """Container/orchestrator health endpoint for Docker, EC2, and load balancers."""
    return {
        "status": "healthy",
        "service": "chaos-control-plane",
        "deployment_mode": DEPLOYMENT_MODE,
        "cloud_provider": CLOUD_PROVIDER,
        "docker_runtime_connected": injector.connected,
        "timestamp": time.time(),
    }


@app.get("/api/config")
async def get_runtime_config():
    return {
        "deployment_mode": DEPLOYMENT_MODE,
        "cloud_provider": CLOUD_PROVIDER,
        "auth_required_for_controls": bool(CHAOS_API_TOKEN),
        "gateway_url": GATEWAY_URL,
        "docker_runtime_connected": injector.connected,
    }

@app.get("/api/status")
async def get_system_status():
    """Returns live telemetry, service statuses, active faults, and circuit breaker status."""
    return {
        "telemetry": monitor.get_latest_status(),
        "circuit_breaker": {
            "state": circuit_breaker.state,
            "consecutive_breaches": circuit_breaker.consecutive_breaches,
            "last_trip_event": circuit_breaker.last_trip_event
        },
        "active_experiment": ACTIVE_EXPERIMENT,
        "active_faults": injector.active_faults,
        "timestamp": time.time()
    }

@app.get("/api/experiments")
def get_experiments():
    return scheduler.list_experiments()

@app.post("/api/experiments/{exp_id}/run")
async def run_experiment(exp_id: str, background_tasks: BackgroundTasks, _: None = Depends(require_control_token)):
    global ACTIVE_EXPERIMENT
    if ACTIVE_EXPERIMENT and ACTIVE_EXPERIMENT.get("status") == "RUNNING":
        raise HTTPException(status_code=409, detail="An experiment is already in progress.")

    exp_def = scheduler.get_experiment(exp_id)
    if not exp_def:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found.")

    ACTIVE_EXPERIMENT = {
        "id": exp_def.id,
        "name": exp_def.name,
        "target": exp_def.target,
        "fault_type": exp_def.fault_type,
        "started_at": time.time(),
        "duration_seconds": exp_def.duration_seconds,
        "status": "RUNNING"
    }

    background_tasks.add_task(run_experiment_worker, exp_def)
    return {"status": "LAUNCHED", "experiment": ACTIVE_EXPERIMENT}

@app.post("/api/experiments/stop")
def stop_experiment(_: None = Depends(require_control_token)):
    global ACTIVE_EXPERIMENT
    if ACTIVE_EXPERIMENT:
        ACTIVE_EXPERIMENT["status"] = "MANUALLY_STOPPED"
    rollback_res = injector.rollback_all()
    circuit_breaker.reset()
    log_event("WARN", "Manual stop initiated. Emergency rollback applied.", rollback_res)
    return {"status": "STOPPED", "rollback": rollback_res}

@app.post("/api/rollback")
def manual_rollback(_: None = Depends(require_control_token)):
    """Safety hatch for immediate manual rollback of all faults."""
    global ACTIVE_EXPERIMENT
    if ACTIVE_EXPERIMENT:
        ACTIVE_EXPERIMENT["status"] = "ROLLED_BACK"
    res = injector.rollback_all()
    circuit_breaker.reset()
    log_event("SUCCESS", "Manual emergency rollback executed for all services.", res)
    return {"status": "SUCCESS", "details": res}

@app.get("/api/logs")
def get_logs():
    return list(EVENT_LOGS)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
