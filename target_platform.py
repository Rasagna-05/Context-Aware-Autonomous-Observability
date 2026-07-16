import uvicorn
import random
from fastapi import FastAPI, Request
from typing import Dict

app = FastAPI(
    title="Cisco Hackathon Target Platform",
    description="The production microservice target being monitored.",
    version="2.2.0"
)

# In-memory metrics counters
metrics_state = {
    "total_reqs": 0,
    "login_attempts": 0,
    "login_success": 0,
    "internal_rpcs": 0
}

# Control plane variables
system_config = {
    "retry_config": 1,
    "botnet_active": False
}

@app.get("/stream")
async def get_stream(request: Request):
    """Increments total requests and internal downstream RPCs based on retry config."""
    # Drop traffic if botnet request and edge isolation is active
    is_botnet = request.headers.get("x-botnet") == "true"
    if is_botnet and not system_config["botnet_active"]:
        return {"status": "RATE_LIMITED"}

    metrics_state["total_reqs"] += 1
    metrics_state["internal_rpcs"] += system_config["retry_config"]
    return {"status": "STREAMING"}

@app.post("/login")
async def post_login(request: Request):
    """Authentication endpoint. Discards botnet requests if mitigation is applied."""
    is_botnet = request.headers.get("x-botnet") == "true"
    if is_botnet and not system_config["botnet_active"]:
        return {"status": "RATE_LIMITED"}

    metrics_state["total_reqs"] += 1
    metrics_state["login_attempts"] += 1
    metrics_state["internal_rpcs"] += system_config["retry_config"]

    # Logins from botnet script fail. Legitimate logins succeed.
    if is_botnet:
        success = False
    else:
        success = True
        metrics_state["login_success"] += 1

    return {"authenticated": success}

@app.post("/admin/config")
async def update_config(request: Request):
    """Configure system retry policies."""
    try:
        payload = await request.json()
        if "max_retries" in payload:
            system_config["retry_config"] = int(payload["max_retries"])
    except Exception:
        pass
    return {"status": "CONFIG_UPDATED", "config": system_config}

@app.post("/admin/botnet")
async def toggle_botnet(request: Request):
    """Toggle the botnet attack simulation state."""
    try:
        payload = await request.json()
        if "active" in payload:
            system_config["botnet_active"] = bool(payload["active"])
    except Exception:
        pass
    return {"status": "BOTNET_STATE_CHANGED", "botnet_active": system_config["botnet_active"]}

@app.get("/metrics")
async def get_metrics():
    """Returns rolling telemetry metrics with ambient baseline load, and flushes counters."""
    
    # Generate healthy ambient noise traffic (450 to 750 requests/sec)
    ambient_reqs = random.randint(450, 750)
    ambient_logins = random.randint(15, 30)
    ambient_success = int(ambient_logins * 0.96) # Healthy auth success baseline (96%)
    
    total_reqs = metrics_state["total_reqs"] + ambient_reqs
    login_attempts = metrics_state["login_attempts"] + ambient_logins
    login_success = metrics_state["login_success"] + ambient_success
    internal_rpcs = metrics_state["internal_rpcs"] + (ambient_reqs * system_config["retry_config"])
    
    response_metrics = {
        "total_reqs": total_reqs,
        "login_attempts": login_attempts,
        "login_success": login_success,
        "internal_rpcs": internal_rpcs,
        "botnet_active": system_config["botnet_active"],
        "retry_config": system_config["retry_config"]
    }
    
    # Flush counters to 0
    metrics_state["total_reqs"] = 0
    metrics_state["login_attempts"] = 0
    metrics_state["login_success"] = 0
    metrics_state["internal_rpcs"] = 0
    
    return response_metrics

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
