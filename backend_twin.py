import random
import time
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Cisco Accelerated Observability Digital Twin Backend",
    description="Maintains physical simulation telemetry state and handles causal remediations",
    version="2.0.0"
)

# Global twin state
TWIN_STATE = {
    "current_context": "NORMAL",
    "legitimate_fans": 1200,
    "botnet_load": 0,
    "retry_factor": 1.0,
    "latency_base": 45,
    "active_mitigations": []
}

class MutatePayload(BaseModel):
    current_context: str = None
    legitimate_fans: int = None
    botnet_load: int = None
    retry_factor: float = None
    latency_base: int = None

class RemediatePayload(BaseModel):
    action: str

@app.post("/api/state/mutate")
def mutate_state(payload: MutatePayload):
    """Mutate state variables from terminal trigger scripts."""
    if payload.current_context is not None:
        TWIN_STATE["current_context"] = payload.current_context
    if payload.legitimate_fans is not None:
        TWIN_STATE["legitimate_fans"] = payload.legitimate_fans
    if payload.botnet_load is not None:
        TWIN_STATE["botnet_load"] = payload.botnet_load
        # Automatically deactivate isolation if a new botnet load is set
        if payload.botnet_load > 0 and "isolate_botnet" in TWIN_STATE["active_mitigations"]:
            TWIN_STATE["active_mitigations"].remove("isolate_botnet")
    if payload.retry_factor is not None:
        TWIN_STATE["retry_factor"] = payload.retry_factor
        # Automatically deactivate config rollback if a new fault factor is set
        if payload.retry_factor > 1.0 and "rollback_config" in TWIN_STATE["active_mitigations"]:
            TWIN_STATE["active_mitigations"].remove("rollback_config")
    if payload.latency_base is not None:
        TWIN_STATE["latency_base"] = payload.latency_base
        
    return {"status": "MUTATED", "state": TWIN_STATE}

@app.post("/api/remediate")
def remediate_twin(payload: RemediatePayload):
    """Appends mitigation action and mutates state dynamically (causal feedback)."""
    action = payload.action
    if action not in TWIN_STATE["active_mitigations"]:
        TWIN_STATE["active_mitigations"].append(action)
        
    if action == "isolate_botnet":
        TWIN_STATE["botnet_load"] = 0
    elif action == "rollback_config":
        TWIN_STATE["retry_factor"] = 1.0
        TWIN_STATE["latency_base"] = 45
        
    return {"status": "REMEDIATED", "active_mitigations": TWIN_STATE["active_mitigations"], "state": TWIN_STATE}

@app.get("/api/telemetry")
def get_telemetry():
    """Generates rolling telemetry metrics with +/- 3% jitter for the live charts."""
    # Ensure mitigations are applied if active
    if "isolate_botnet" in TWIN_STATE["active_mitigations"]:
        TWIN_STATE["botnet_load"] = 0
    if "rollback_config" in TWIN_STATE["active_mitigations"]:
        TWIN_STATE["retry_factor"] = 1.0
        TWIN_STATE["latency_base"] = 45

    legit = TWIN_STATE["legitimate_fans"]
    botnet = TWIN_STATE["botnet_load"]
    retry_mult = TWIN_STATE["retry_factor"]
    lat_base = TWIN_STATE["latency_base"]
    ctx = TWIN_STATE["current_context"]

    # Calculate baseline total traffic
    total_requests = legit + botnet
    expected_event_load = 12000 if ctx == "MERCH_DROP" else 1200
    
    # Invariant ratios: r1 (CPU), r2 (Auth), r3 (Entropy), r4 (RPC), r5 (Error Rate)
    # CPU scales with load and retries
    r1_cpu = min(0.99, 0.35 + (total_requests / 120000) * 0.4 + (retry_mult - 1.0) * 0.05)
    
    # Auth Success
    if botnet == 0:
        r2_auth = 0.96
        r3_entropy = 4.6
        r5_error = 0.02
    else:
        r2_auth = max(0.14, (legit / total_requests) * 0.9)
        r3_entropy = max(1.2, 4.6 - (botnet / 8000))
        r5_error = 0.14
        
    r4_rpc = 1.3 * retry_mult
    if r4_rpc > 3.0:
        r1_cpu = min(0.99, r1_cpu + 0.3)
        r5_error = max(r5_error, 0.65)
        # Retry storm loops cause traffic spikes
        total_requests = int(total_requests * (1.0 + (retry_mult - 1.0) * 0.8))

    # Latency calculation
    latency = lat_base
    if r4_rpc > 3.0:
        latency = lat_base + (retry_mult - 1.0) * 220.0
    elif ctx == "MERCH_DROP":
        latency = lat_base + 80.0

    # Add +/- 3% random jitter
    jitter = lambda val, pct: val * random.uniform(1.0 - pct, 1.0 + pct)
    
    total_requests_jit = max(10, int(jitter(total_requests, 0.03)))
    expected_load_jit = max(10, int(jitter(expected_event_load, 0.03)))
    unexplained_residual = max(0, total_requests_jit - expected_load_jit)
    
    r1_jit = min(1.0, max(0.0, jitter(r1_cpu, 0.02)))
    r2_jit = min(1.0, max(0.0, jitter(r2_auth, 0.02)))
    r3_jit = min(6.0, max(0.0, jitter(r3_entropy, 0.02)))
    r4_jit = max(0.0, jitter(r4_rpc, 0.02))
    r5_jit = min(1.0, max(0.0, jitter(r5_error, 0.02)))
    latency_jit = max(5.0, jitter(latency, 0.03))

    return {
        "timestamp": time.time(),
        "current_context": ctx,
        "active_mitigations": TWIN_STATE["active_mitigations"],
        "legitimate_fans": legit,
        "botnet_load": botnet,
        "retry_factor": retry_mult,
        "latency_base": lat_base,
        "total_requests": total_requests_jit,
        "expected_event_load": expected_load_jit,
        "unexplained_residual": unexplained_residual,
        "r1": round(r1_jit, 4),
        "r2": round(r2_jit, 4),
        "r3": round(r3_jit, 4),
        "r4": round(r4_jit, 4),
        "r5": round(r5_jit, 4),
        "p95_latency": round(latency_jit, 2)
    }
