import time
from typing import Dict, Any, Optional

try:
    import docker
except ImportError:  # Allows the dashboard to expose a clear runtime status before deps are installed.
    docker = None

class FaultInjector:
    def __init__(self):
        self.client = None
        self.connected = False
        try:
            self.client = docker.from_env() if docker else None
            if self.client is not None:
                self.client.ping()
            self.connected = self.client is not None
            if not self.connected:
                raise RuntimeError("Python Docker SDK is not installed")
        except Exception as e:
            print(f"[FaultInjector] Warning: Docker socket connection failed: {e}")
            self.client = None
            self.connected = False

        # In-memory registry of active faults for guaranteed rollback
        # Key: container_name -> Dict with fault details & rollback instructions
        self.active_faults: Dict[str, Dict[str, Any]] = {}

    def find_container(self, name_pattern: str):
        if not self.client:
            return None
        try:
            # First try exact match
            try:
                return self.client.containers.get(name_pattern)
            except docker.errors.NotFound:
                pass

            # Next try substring search in running or stopped containers
            all_containers = self.client.containers.list(all=True)
            for c in all_containers:
                if name_pattern in c.name:
                    return c
            return None
        except Exception as e:
            print(f"[FaultInjector] Error finding container {name_pattern}: {e}")
            return None

    def inject_fault(self, target_name: str, fault_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        container = self.find_container(target_name)
        if not container:
            raise RuntimeError(f"Target container '{target_name}' not found in Docker runtime.")

        t0 = time.time()
        record = {
            "target": container.name,
            "target_id": container.id,
            "fault_type": fault_type,
            "params": params,
            "injected_at": t0,
            "status": "ACTIVE"
        }

        if fault_type in ("container_kill", "container_stop"):
            # Simulate sudden compute node crash / termination
            container.stop(timeout=1)
            record["rollback_action"] = "restart_container"

        elif fault_type == "network_latency":
            # Simulate cross-AZ network latency using Linux tc/netem
            delay_ms = params.get("delay_ms", 500)
            # Clear any existing tc qdisc first
            container.exec_run("tc qdisc del dev eth0 root")
            # Apply netem delay
            cmd = f"tc qdisc add dev eth0 root netem delay {delay_ms}ms"
            res = container.exec_run(cmd)
            if res.exit_code != 0:
                print(f"[FaultInjector] tc netem warning: {res.output.decode('utf-8', errors='ignore')}")
            record["rollback_action"] = "clear_tc"

        elif fault_type == "network_partition":
            # Simulate VPC Security Group blackhole / packet drop
            # Drop incoming packets on eth0
            cmd = "iptables -A INPUT -i eth0 -j DROP"
            res = container.exec_run(cmd)
            if res.exit_code != 0:
                # Fallback: drop all
                container.exec_run("iptables -P INPUT DROP")
            record["rollback_action"] = "flush_iptables"

        elif fault_type == "cpu_stress":
            # Simulate noisy neighbor / 100% CPU exhaustion. Keep explicit PIDs so
            # rollback only stops workers created by this experiment.
            cmd = (
                "sh -c 'rm -f /tmp/chaos-cpu-pids; "
                "(while :; do :; done) & p1=$!; "
                "(while :; do :; done) & p2=$!; "
                "printf \"%s\\n%s\\n\" $p1 $p2 > /tmp/chaos-cpu-pids; wait'"
            )
            container.exec_run(cmd, detach=True)
            record["rollback_action"] = "kill_cpu_stress"

        else:
            raise ValueError(f"Unsupported fault type: {fault_type}")

        self.active_faults[container.name] = record
        return {
            "status": "INJECTED",
            "target": container.name,
            "fault_type": fault_type,
            "duration_ms": round((time.time() - t0) * 1000, 2)
        }

    def rollback_container(self, target_name: str) -> Dict[str, Any]:
        container = self.find_container(target_name)
        if not container:
            return {"status": "SKIPPED", "reason": f"Container {target_name} not found"}

        fault_info = self.active_faults.get(container.name, {})
        action = fault_info.get("rollback_action")
        t0 = time.time()

        try:
            # Always ensure container is running
            container.reload()
            if container.status != "running":
                container.start()
                time.sleep(1.0)

            # Flush iptables and clear tc qdisc unconditionally for clean state
            container.exec_run("iptables -F")
            container.exec_run("iptables -P INPUT ACCEPT")
            container.exec_run("tc qdisc del dev eth0 root")
            # Kill only the CPU workers owned by this injector, if present.
            container.exec_run(
                "sh -c 'if [ -f /tmp/chaos-cpu-pids ]; then "
                "kill -9 $(cat /tmp/chaos-cpu-pids) 2>/dev/null || true; "
                "rm -f /tmp/chaos-cpu-pids; fi'"
            )

            if container.name in self.active_faults:
                del self.active_faults[container.name]

            return {
                "status": "RESTORED",
                "target": container.name,
                "recovery_time_ms": round((time.time() - t0) * 1000, 2)
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "target": container.name,
                "error": str(e)
            }

    def rollback_all(self) -> Dict[str, Any]:
        """Safety net: rolls back all active faults and verifies clean system state."""
        results = {}
        target_keys = list(self.active_faults.keys())
        
        # If no explicit active faults registered, still check standard containers to ensure clean state
        if not target_keys and self.client:
            for pattern in ["inventory-service", "order-service", "gateway"]:
                c = self.find_container(pattern)
                if c:
                    target_keys.append(c.name)

        for target in target_keys:
            results[target] = self.rollback_container(target)

        self.active_faults.clear()
        return {
            "status": "ALL_ROLLED_BACK",
            "results": results
        }
