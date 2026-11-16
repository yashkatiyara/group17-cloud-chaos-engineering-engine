import time
from typing import Dict, Any, Optional
from core.injector import FaultInjector
from core.scheduler import ExperimentDefinition

class CircuitBreaker:
    STATE_CLOSED = "CLOSED"           # Normal operation, no trip
    STATE_MONITORING = "MONITORING"   # Chaos experiment active, watching metrics
    STATE_TRIPPED = "TRIPPED"         # SLO breached, emergency rollback engaged

    def __init__(self, injector: FaultInjector):
        self.injector = injector
        self.state = self.STATE_CLOSED
        self.consecutive_breaches = 0
        self.last_trip_event: Optional[Dict[str, Any]] = None

    def reset(self):
        self.state = self.STATE_CLOSED
        self.consecutive_breaches = 0

    def start_monitoring(self):
        self.state = self.STATE_MONITORING
        self.consecutive_breaches = 0

    def evaluate(self, metrics: Dict[str, Any], experiment: ExperimentDefinition) -> Dict[str, Any]:
        """Evaluates live metrics against experiment steady-state hypothesis."""
        if self.state != self.STATE_MONITORING:
            return {"tripped": False, "state": self.state}

        error_rate = metrics.get("error_rate_pct", 0.0)
        p95_latency = metrics.get("latency_p95_ms", 0.0)
        instant_latency = metrics.get("instant_latency_ms", 0.0)
        is_healthy = metrics.get("overall_healthy", True)

        breach_reasons = []
        if error_rate > experiment.max_error_rate_percent:
            breach_reasons.append(
                f"Error rate {error_rate}% exceeded threshold {experiment.max_error_rate_percent}%"
            )
        if p95_latency > experiment.max_p95_latency_ms:
            breach_reasons.append(
                f"P95 latency {p95_latency}ms exceeded threshold {experiment.max_p95_latency_ms}ms"
            )
        if not is_healthy:
            breach_reasons.append("Downstream service unhealthy or unreachable")

        if breach_reasons:
            self.consecutive_breaches += 1
        else:
            self.consecutive_breaches = max(0, self.consecutive_breaches - 1)

        # Check if consecutive breach threshold is met
        if self.consecutive_breaches >= experiment.consecutive_breaches_allowed:
            # Trip the circuit breaker and execute instant rollback!
            t0 = time.time()
            self.state = self.STATE_TRIPPED
            
            # Execute emergency rollback
            rollback_result = self.injector.rollback_all()
            rollback_duration_ms = round((time.time() - t0) * 1000, 2)

            self.last_trip_event = {
                "timestamp": time.time(),
                "experiment_id": experiment.id,
                "reasons": breach_reasons,
                "metrics_snapshot": {
                    "error_rate_pct": error_rate,
                    "latency_p95_ms": p95_latency,
                    "instant_latency_ms": instant_latency
                },
                "rollback_duration_ms": rollback_duration_ms,
                "rollback_result": rollback_result
            }

            return {
                "tripped": True,
                "state": self.STATE_TRIPPED,
                "trip_event": self.last_trip_event
            }

        return {
            "tripped": False,
            "state": self.STATE_MONITORING,
            "consecutive_breaches": self.consecutive_breaches
        }
