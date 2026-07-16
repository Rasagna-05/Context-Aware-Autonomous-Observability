import random
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Cisco Hackathon Observability Backend",
    description="Event-Driven State Machine Digital Twin Service",
    version="1.0.0"
)

# Global State Dictionary
SYSTEM_STATE = {
    "context": "NORMAL",
    "legitimate_fans": 1000,
    "botnet_ips": 0,
    "retry_multiplier": 1.0,
    "mitigation_applied": False
}

class MutationPayload(BaseModel):
    context: str = None
    legitimate_fans: int = None
    botnet_ips: int = None
    retry_multiplier: float = None
    mitigation_applied: bool = None

@app.post("/mutate")
def mutate_state(payload: MutationPayload):
    """Mutate global state from terminal scripts or interactive actions."""
    if payload.context is not None:
        SYSTEM_STATE["context"] = payload.context
    if payload.legitimate_fans is not None:
        SYSTEM_STATE["legitimate_fans"] = payload.legitimate_fans
    if payload.botnet_ips is not None:
        SYSTEM_STATE["botnet_ips"] = payload.botnet_ips
        # Automatically deactivate mitigation when an attack is injected
        if payload.botnet_ips > 0:
            SYSTEM_STATE["mitigation_applied"] = False
    if payload.retry_multiplier is not None:
        SYSTEM_STATE["retry_multiplier"] = payload.retry_multiplier
        # Automatically deactivate mitigation when a config fault is injected
        if payload.retry_multiplier > 1.0:
            SYSTEM_STATE["mitigation_applied"] = False
    if payload.mitigation_applied is not None:
        SYSTEM_STATE["mitigation_applied"] = payload.mitigation_applied
        
    return {"status": "SUCCESS", "current_state": SYSTEM_STATE}

@app.get("/telemetry")
def get_telemetry():
    """Generates real-time, jitter-infused observability metrics based on state."""
    # Apply causal recovery loop if mitigation has been applied
    if SYSTEM_STATE["mitigation_applied"]:
        SYSTEM_STATE["botnet_ips"] = 0
        SYSTEM_STATE["retry_multiplier"] = 1.0
        
    legit = SYSTEM_STATE["legitimate_fans"]
    botnet = SYSTEM_STATE["botnet_ips"]
    retry_mult = SYSTEM_STATE["retry_multiplier"]
    
    # Calculate baseline values
    total_reqs = legit + botnet
    expected_reqs = legit
    
    # Invariant calculations
    # r1: CPU Load, r2: Auth Success, r3: Payload Entropy, r4: RPC Amplification, r5: Error Rate
    if botnet > 0:
        r2 = 0.95 * (legit / total_reqs) # login success drops relative to botnet size
        r3 = 1.2 # Hard botnet signature
        r1_cpu = 0.84
        r5_err = 0.15
        latency = 220.0
    else:
        r2 = 0.95
        r3 = 4.5
        r1_cpu = 0.32 if legit < 5000 else 0.72
        r5_err = 0.02
        latency = 78.0 if legit < 5000 else 165.0
        
    r4 = 1.2 * retry_mult
    if r4 > 5.0:
        r1_cpu = 0.98
        r5_err = 0.68
        latency = 2500.0
        # Retry storm amplifies total requests due to infinite cascades
        total_reqs = int(total_reqs * (1.0 + (retry_mult - 1.0) * 0.7))
        
    # Inject ~5% random jitter to make telemetry graphs look active/alive
    jitter = lambda val, pct: val * random.uniform(1.0 - pct, 1.0 + pct)
    
    total_reqs_jit = max(10, int(jitter(total_reqs, 0.04)))
    expected_reqs_jit = max(10, int(jitter(expected_reqs, 0.04)))
    
    r1_jit = min(1.0, max(0.0, r1_cpu + random.uniform(-0.02, 0.02)))
    r2_jit = min(1.0, max(0.0, r2 + random.uniform(-0.015, 0.015)))
    r3_jit = min(6.0, max(0.0, r3 + random.uniform(-0.1, 0.1)))
    r4_jit = max(0.0, r4 + random.uniform(-0.04, 0.04))
    r5_jit = min(1.0, max(0.0, r5_err + random.uniform(-0.008, 0.008)))
    latency_jit = max(5.0, latency + random.uniform(-6.0, 6.0))
    
    # Calculate residual
    residual = max(0, total_reqs_jit - expected_reqs_jit)
    
    return {
        "context": SYSTEM_STATE["context"],
        "mitigation_applied": SYSTEM_STATE["mitigation_applied"],
        "legitimate_fans": legit,
        "botnet_ips": botnet,
        "retry_multiplier": retry_mult,
        "total_requests": total_reqs_jit,
        "expected_requests": expected_reqs_jit,
        "residual": residual,
        "r1": round(r1_jit, 4),
        "r2": round(r2_jit, 4),
        "r3": round(r3_jit, 4),
        "r4": round(r4_jit, 4),
        "r5": round(r5_jit, 4),
        "p95_latency": round(latency_jit, 2)
    }
