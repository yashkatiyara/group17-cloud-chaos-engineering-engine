// Real-time polling and interactive control for Chaos Dashboard

let lastLogCount = 0;

function controlHeaders() {
    const token = localStorage.getItem("chaos_api_token");
    return token ? {"X-Chaos-Token": token} : {};
}

function saveToken() {
    const input = document.getElementById("control-token");
    if (input.value.trim()) {
        localStorage.setItem("chaos_api_token", input.value.trim());
        input.value = "";
        alert("Control token saved in this browser session.");
    }
}

async function fetchStatus() {
    try {
        const resp = await fetch("/api/status");
        if (!resp.ok) return;
        const data = await resp.json();
        
        updateTopology(data.telemetry, data.active_faults);
        updateGauges(data.telemetry, data.circuit_breaker);
        updateCircuitBreaker(data.circuit_breaker, data.active_experiment);
    } catch (e) {
        console.error("Error fetching status:", e);
    }
}

async function fetchLogs() {
    try {
        const resp = await fetch("/api/logs");
        if (!resp.ok) return;
        const logs = await resp.json();
        
        const terminal = document.getElementById("terminal-logs");
        if (logs.length > lastLogCount) {
            terminal.innerHTML = "";
            logs.forEach(log => {
                const line = document.createElement("div");
                line.className = `log-line log-${log.level}`;
                line.innerHTML = `<span class="log-time">[${log.time_str}]</span> [${log.level}] ${log.message}`;
                terminal.appendChild(line);
            });
            terminal.scrollTop = terminal.scrollHeight;
            lastLogCount = logs.length;
        }
    } catch (e) {
        console.error("Error fetching logs:", e);
    }
}

function updateTopology(telemetry, activeFaults) {
    if (!telemetry) return;

    // Gateway
    const gwStatus = telemetry.gateway || "UNKNOWN";
    const badgeGw = document.getElementById("badge-gateway");
    const valGwStatus = document.getElementById("gateway-status");
    const valGwLat = document.getElementById("gateway-latency");
    
    badgeGw.textContent = gwStatus;
    badgeGw.className = `badge badge-${gwStatus.toLowerCase()}`;
    valGwStatus.textContent = gwStatus;
    valGwLat.textContent = `${telemetry.instant_latency_ms || 0} ms`;

    // Order Service
    const ordStatus = telemetry.order_service || "UNKNOWN";
    const badgeOrd = document.getElementById("badge-order");
    const valOrdStatus = document.getElementById("order-status");
    
    badgeOrd.textContent = ordStatus;
    badgeOrd.className = `badge badge-${ordStatus.toLowerCase()}`;
    valOrdStatus.textContent = ordStatus;

    // Inventory Service
    const invStatus = telemetry.inventory_service || "UNKNOWN";
    const badgeInv = document.getElementById("badge-inventory");
    const valInvStatus = document.getElementById("inventory-status");
    const valInvFault = document.getElementById("inventory-fault");
    
    badgeInv.textContent = invStatus;
    badgeInv.className = `badge badge-${invStatus.toLowerCase()}`;
    valInvStatus.textContent = invStatus;

    // Active Fault Detection
    let faultDesc = "None";
    if (activeFaults) {
        for (const [target, info] of Object.entries(activeFaults)) {
            if (target.includes("inventory")) {
                faultDesc = `${info.fault_type}`;
            }
        }
    }
    valInvFault.textContent = faultDesc;
}

function updateGauges(telemetry, cb) {
    if (!telemetry) return;

    // P95 Latency
    const p95 = telemetry.latency_p95_ms || 0;
    document.getElementById("val-p95").textContent = `${p95} ms`;
    const barP95 = document.getElementById("bar-p95");
    const p95Percent = Math.min((p95 / 800) * 100, 100);
    barP95.style.width = `${p95Percent}%`;
    barP95.style.background = p95 > 800 ? "var(--red)" : p95 > 400 ? "var(--yellow)" : "var(--primary)";

    // Error Rate
    const errRate = telemetry.error_rate_pct || 0;
    document.getElementById("val-error-rate").textContent = `${errRate}%`;
    const barErr = document.getElementById("bar-error");
    const errPercent = Math.min((errRate / 15) * 100, 100);
    barErr.style.width = `${errPercent}%`;
    barErr.style.background = errRate > 15 ? "var(--red)" : errRate > 5 ? "var(--yellow)" : "var(--green)";
}

function updateCircuitBreaker(cb, activeExp) {
    const cbBadge = document.getElementById("cb-badge");
    const cbVal = document.getElementById("val-cb-state");
    const cbDesc = document.getElementById("val-cb-desc");
    const cbBar = document.getElementById("bar-cb");
    const banner = document.getElementById("alert-banner");
    const alertText = document.getElementById("alert-text");

    if (!cb) return;

    cbBadge.textContent = `Circuit Breaker: ${cb.state}`;
    cbVal.textContent = cb.state;

    if (cb.state === "TRIPPED") {
        cbBadge.className = "badge badge-tripped";
        cbVal.style.color = "var(--red)";
        cbDesc.textContent = "SLO Breached • Emergency Rollback Active";
        cbBar.style.background = "var(--red)";
        
        banner.className = "banner badge-tripped";
        banner.style.display = "flex";
        alertText.textContent = "🚨 CRITICAL: Circuit Breaker tripped due to SLO breach. Auto-rollback executed!";
    } else if (cb.state === "MONITORING") {
        cbBadge.className = "badge badge-warn";
        cbVal.style.color = "var(--yellow)";
        cbDesc.textContent = "Active Experiment In Progress";
        cbBar.style.background = "var(--yellow)";
        
        if (activeExp) {
            banner.className = "banner badge-warn";
            banner.style.display = "flex";
            alertText.textContent = `⚡ Running Chaos Experiment: ${activeExp.name} on target '${activeExp.target}'`;
        }
    } else {
        cbBadge.className = "badge badge-normal";
        cbVal.style.color = "var(--green)";
        cbDesc.textContent = "Automatic Rollback Armed";
        cbBar.style.background = "var(--green)";
        banner.style.display = "none";
    }
}

async function runExperiment(id) {
    try {
        const resp = await fetch(`/api/experiments/${id}/run`, { method: "POST", headers: controlHeaders() });
        if (resp.status === 409) {
            alert("An experiment is already in progress!");
            return;
        }
        if (resp.status === 401) {
            alert("This cloud control plane requires the X-Chaos-Token. Enter it above first.");
            return;
        }
        if (!resp.ok) {
            const err = await resp.json();
            alert(`Error launching experiment: ${err.detail || resp.statusText}`);
            return;
        }
        fetchStatus();
        fetchLogs();
    } catch (e) {
        alert("Failed to run experiment: " + e);
    }
}

async function triggerRollback() {
    try {
        const resp = await fetch("/api/rollback", { method: "POST", headers: controlHeaders() });
        if (resp.ok) {
            fetchStatus();
            fetchLogs();
        } else if (resp.status === 401) {
            alert("This cloud control plane requires the X-Chaos-Token. Enter it above first.");
        }
    } catch (e) {
        alert("Rollback failed: " + e);
    }
}

function clearLogs() {
    document.getElementById("terminal-logs").innerHTML = "";
    lastLogCount = 0;
}

// Start polling
setInterval(fetchStatus, 1000);
setInterval(fetchLogs, 1000);
fetchStatus();
fetchLogs();
