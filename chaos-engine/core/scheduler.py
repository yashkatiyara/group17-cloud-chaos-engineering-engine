import os
import yaml
from typing import Dict, Any, List

class ExperimentDefinition:
    def __init__(self, data: Dict[str, Any], filepath: str = ""):
        self.id = data.get("id", os.path.basename(filepath).replace(".yaml", "").replace(".yml", ""))
        self.name = data.get("name", "Unnamed Experiment")
        self.description = data.get("description", "")
        self.target = data.get("target", "inventory-service")
        
        # Fault configuration
        fault_cfg = data.get("fault", {})
        self.fault_type = fault_cfg.get("type", "container_kill")
        self.duration_seconds = fault_cfg.get("duration_seconds", 15)
        self.delay_ms = fault_cfg.get("delay_ms", 500)
        self.loss_percent = fault_cfg.get("loss_percent", 0)
        self.cpu_percent = fault_cfg.get("cpu_percent", 100)
        
        # Steady state hypothesis
        steady_cfg = data.get("steady_state_hypothesis", {})
        self.max_error_rate_percent = float(steady_cfg.get("max_error_rate_percent", 15.0))
        self.max_p95_latency_ms = float(steady_cfg.get("max_p95_latency_ms", 800.0))
        self.probe_interval_seconds = float(steady_cfg.get("probe_interval_seconds", 1.0))
        self.consecutive_breaches_allowed = int(steady_cfg.get("consecutive_breaches_allowed", 2))
        
        # Rollback settings
        rollback_cfg = data.get("rollback", {})
        self.auto_rollback = rollback_cfg.get("auto_rollback", True)
        self.recovery_action = rollback_cfg.get("recovery_action", "auto")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target": self.target,
            "fault": {
                "type": self.fault_type,
                "duration_seconds": self.duration_seconds,
                "delay_ms": self.delay_ms,
                "loss_percent": self.loss_percent,
                "cpu_percent": self.cpu_percent
            },
            "steady_state_hypothesis": {
                "max_error_rate_percent": self.max_error_rate_percent,
                "max_p95_latency_ms": self.max_p95_latency_ms,
                "probe_interval_seconds": self.probe_interval_seconds,
                "consecutive_breaches_allowed": self.consecutive_breaches_allowed
            },
            "rollback": {
                "auto_rollback": self.auto_rollback,
                "recovery_action": self.recovery_action
            }
        }

class ExperimentScheduler:
    def __init__(self, experiments_dir: str):
        self.experiments_dir = experiments_dir
        self.experiments: Dict[str, ExperimentDefinition] = {}
        self.reload_experiments()

    def reload_experiments(self):
        self.experiments.clear()
        if not os.path.exists(self.experiments_dir):
            return
        for fname in sorted(os.listdir(self.experiments_dir)):
            if fname.endswith(".yaml") or fname.endswith(".yml"):
                fpath = os.path.join(self.experiments_dir, fname)
                try:
                    with open(fpath, "r") as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            exp = ExperimentDefinition(data, filepath=fpath)
                            self.experiments[exp.id] = exp
                except Exception as e:
                    print(f"[Scheduler] Error loading experiment {fname}: {e}")

    def list_experiments(self) -> List[Dict[str, Any]]:
        return [exp.to_dict() for exp in self.experiments.values()]

    def get_experiment(self, exp_id: str) -> ExperimentDefinition:
        return self.experiments.get(exp_id)
