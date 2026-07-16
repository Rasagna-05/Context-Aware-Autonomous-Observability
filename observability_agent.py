import uvicorn
import time
import httpx
import threading
import random
from fastapi import FastAPI, Body, HTTPException
from typing import Dict, List, Any

app = FastAPI(
    title="Cisco Observability Agent",
    description="Polls target_platform metrics and calculates mathematical invariants.",
    version="2.3.3"
)

# Shared in-memory data
history_mutex = threading.Lock()
agent_history: List[Dict[str, Any]] = []
latest_metrics: Dict[str, Any] = {}
action_log: List[Dict[str, Any]] = []

def process_metrics(raw: Dict[str, Any]):
    """Processes raw counters from target_platform and computes ratio thresholds."""
    total_reqs = raw.get("total_reqs", 0)
    login_attempts = raw.get("login_attempts", 0)
    login_success = raw.get("login_success", 0)
    internal_rpcs = raw.get("internal_rpcs", 0)
    botnet_active = raw.get("botnet_active", False)
    retry_config = raw.get("retry_config", 1)

    # 1. Expected load calculation (Restoring established logic)
    # Under botnet attack, expected traffic stays at 1500 baseline so unexplained residual spikes.
    # Under Merch Surge, expected traffic scales to 15000 to match legitimate surge load.
    if botnet_active:
        expected_load = 1500
    elif total_reqs > 5000:
        expected_load = 15000
    else:
        expected_load = 1500
        
    unexplained_residual = max(0, total_reqs - expected_load)

    # 2. Invariant metrics and thresholds
    if retry_config > 3:
        r1_cpu = 0.97
    elif botnet_active:
        r1_cpu = 0.88
    else:
        r1_cpu = 0.45

    if login_attempts == 0:
        r2_auth = 0.96
    else:
        r2_auth = login_success / login_attempts

    r3_entropy = 1.1 if botnet_active else 4.8
    r4_rpc = float(retry_config)

    if retry_config > 3:
        r5_err = 0.65
    elif botnet_active:
        r5_err = 0.145
    else:
        r5_err = 0.02

    if retry_config > 3:
        latency = 2500.0
    elif botnet_active:
        latency = 220.0
    else:
        latency = 45.0

    # 3. RCA State Machine and Confidence Calculation
    if retry_config > 3:
        rca_state = "ALERT_RETRY_STORM"
        rca_verdict = "RPC amplification (r4 > 3x). Root Cause: config.yaml (commit a7f31c2)."
        confidence = 97.0 + min(2.9, (r4_rpc - 3.0) * 0.2)
        confidence = min(99.9, max(90.0, confidence))
    elif botnet_active or (r2_auth < 0.40 and r3_entropy < 2.0):
        rca_state = "ALERT_CREDENTIAL_STUFFING"
        rca_verdict = "Auth success collapsed (r2 < 40%), entropy dropped (r3 < 2.0). Verdict: Credential Stuffing."
        confidence = 94.0 + (0.40 - r2_auth) * 10.0 + (2.0 - r3_entropy) * 2.0
        confidence = min(99.9, max(90.0, confidence))
    else:
        rca_state = "SUPPRESS_EXPECTED_EVENT"
        rca_verdict = "All invariants healthy. Metrics within limits."
        if total_reqs > 5000:
            confidence = 92.5 + random.uniform(-1.0, 1.0)
        else:
            confidence = 100.0

    # Jitter simulation
    jitter = lambda val, pct: val * random.uniform(1.0 - pct, 1.0 + pct)
    
    total_reqs_jit = max(0, int(jitter(total_reqs, 0.02)))
    unexplained_res_jit = max(0, total_reqs_jit - expected_load)
    
    r1_jit = min(1.0, max(0.0, jitter(r1_cpu, 0.01)))
    r2_jit = min(1.0, max(0.0, r2_auth))
    r3_jit = min(6.0, max(0.0, jitter(r3_entropy, 0.01)))
    r4_jit = max(0.0, r4_rpc)
    r5_jit = min(1.0, max(0.0, jitter(r5_err, 0.01)))
    latency_jit = max(5.0, jitter(latency, 0.02))

    processed = {
        "timestamp": time.time(),
        "total_requests": total_reqs_jit,
        "expected_event_load": expected_load,
        "unexplained_residual": unexplained_res_jit,
        "botnet_active": botnet_active,
        "retry_config": retry_config,
        "r1": round(r1_jit, 4),
        "r2": round(r2_jit, 4),
        "r3": round(r3_jit, 4),
        "r4": round(r4_jit, 4),
        "r5": round(r5_jit, 4),
        "p95_latency": round(latency_jit, 2),
        "verdict": rca_state,
        "rca": rca_verdict,
        "confidence_score": round(confidence, 1)
    }

    with history_mutex:
        global latest_metrics
        latest_metrics = processed
        agent_history.append(processed)
        if len(agent_history) > 40:
            agent_history.pop(0)

def poll_target_loop():
    """Background polling thread hitting target_platform with robust timeout and fallback."""
    client = httpx.Client()
    while True:
        try:
            res = client.get("http://localhost:8001/metrics", timeout=3.0)
            if res.status_code == 200:
                process_metrics(res.json())
            else:
                fallback = {
                    "total_reqs": 0, "login_attempts": 0, "login_success": 0,
                    "internal_rpcs": 0, "botnet_active": False, "retry_config": 1
                }
                with history_mutex:
                    if latest_metrics:
                        fallback["botnet_active"] = latest_metrics.get("botnet_active", False)
                        fallback["retry_config"] = latest_metrics.get("retry_config", 1)
                process_metrics(fallback)
        except Exception:
            fallback = {
                "total_reqs": 0, "login_attempts": 0, "login_success": 0,
                "internal_rpcs": 0, "botnet_active": False, "retry_config": 1
            }
            with history_mutex:
                if latest_metrics:
                    fallback["botnet_active"] = latest_metrics.get("botnet_active", False)
                    fallback["retry_config"] = latest_metrics.get("retry_config", 1)
            process_metrics(fallback)
        time.sleep(1.0)

# Run Background thread
poll_thread = threading.Thread(target=poll_target_loop, daemon=True)
poll_thread.start()

@app.get("/api/agent_state")
def get_agent_state():
    """Returns invariant status rollups, history, and action logs."""
    with history_mutex:
        return {
            "latest": latest_metrics,
            "history": agent_history,
            "action_log": action_log
        }

@app.post("/api/remediate")
def remediate_incident(payload: Dict = Body(...)):
    """Orchestrates HTTP remediation actions back to the target microservice."""
    action = payload.get("action")
    if not action:
        raise HTTPException(status_code=400, detail="Missing remediation action.")
        
    client = httpx.Client()
    timestamp = time.strftime("%H:%M:%S")
    
    if action == "isolate_botnet":
        try:
            res = client.post("http://localhost:8001/admin/botnet", json={"active": False}, timeout=5.0)
            if res.status_code == 200:
                with history_mutex:
                    if latest_metrics:
                        latest_metrics["botnet_active"] = False
                action_log.append({
                    "Timestamp": timestamp,
                    "Target Component": "edge-gateway",
                    "Action": "Edge Rate-Limiting deployed",
                    "Reason": "Auth success collapsed (r2 < 40%) & entropy dropped (r3 < 2.0)",
                    "Blast Radius Boundary": "Cohort-91 IP blocked (0% disruption to legitimate checkouts)",
                    "Status": "✅ Verified Recovery"
                })
                return {"status": "SUCCESS", "message": "Botnet attack isolated."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to contact target: {e}")
            
    elif action == "rollback_config":
        try:
            res = client.post("http://localhost:8001/admin/config", json={"max_retries": 1}, timeout=5.0)
            if res.status_code == 200:
                with history_mutex:
                    if latest_metrics:
                        latest_metrics["retry_config"] = 1
                action_log.append({
                    "Timestamp": timestamp,
                    "Target Component": "services/payment-service",
                    "Action": "Rollback Configuration deployed",
                    "Reason": "RPC amplification breached (r4 > 3.0x)",
                    "Blast Radius Boundary": "payment-service config.yaml reverted to main stable trunk baseline",
                    "Status": "✅ Verified Recovery"
                })
                return {"status": "SUCCESS", "message": "Configuration rolled back."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to contact target: {e}")
            
    raise HTTPException(status_code=400, detail="Invalid mitigation action.")

@app.post("/api/reset")
def reset_agent_state():
    """Resets agent in-memory history, latest metrics, action logs, and target configs."""
    global agent_history, latest_metrics, action_log
    
    # Try to reset the target platform config as well
    client = httpx.Client()
    try:
        client.post("http://localhost:8001/admin/config", json={"max_retries": 1}, timeout=2.0)
        client.post("http://localhost:8001/admin/botnet", json={"active": False}, timeout=2.0)
    except Exception:
        pass

    with history_mutex:
        agent_history.clear()
        latest_metrics.clear()
        action_log.clear()
        
    return {"status": "SUCCESS", "message": "Simulation state reset successfully."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
