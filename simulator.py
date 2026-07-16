import random
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Cisco Observability Hackathon Digital Twin Simulator",
    description="Deterministic 30-tick Digital Twin simulator with mock ML inference and causal feedback loops.",
    version="2.0.0"
)

class RemediationRequest(BaseModel):
    action: str

def generate_telemetry_data(tick: int, active_mitigations: List[str]) -> Dict[str, Any]:
    """
    Generates realistic, noise-injected telemetry data based on the current logical tick
    and any active mitigations. Uses deterministic seeds to ensure run-to-run consistency.
    """
    random_state = random.Random(tick + 100) # Deterministic but tick-dependent noise
    noise = lambda low, high: random_state.uniform(low, high)
    
    # Define current phase and scenario
    if 1 <= tick <= 5:
        scenario = "NORMAL"
        context = "Normal Operations"
        health = "HEALTHY"
    elif 6 <= tick <= 12:
        scenario = "MERCH_DROP_SURGE"
        context = "Merch Drop Active"
        health = "DEGRADED"
    elif 13 <= tick <= 18:
        if "throttle_botnet" in active_mitigations:
            scenario = "CREDENTIAL_STUFFING_MITIGATED"
            context = "Merch Drop Active (Mitigated)"
            health = "HEALTHY"
        else:
            scenario = "CREDENTIAL_STUFFING"
            context = "Merch Drop Active (Anomaly)"
            health = "CRITICAL"
    elif 19 <= tick <= 24:
        scenario = "RECOVERY"
        context = "Post-Event Recovery"
        health = "HEALTHY"
    elif 25 <= tick <= 30:
        if "rollback_config" in active_mitigations:
            scenario = "RETRY_STORM_MITIGATED"
            context = "Normal Operations (Mitigated)"
            health = "HEALTHY"
        else:
            scenario = "RETRY_STORM"
            context = "Internal Config Fault"
            health = "CRITICAL"
    else:
        scenario = "NORMAL"
        context = "Normal Operations"
        health = "HEALTHY"

    # Base baseline values (NORMAL state)
    total_requests = 11000 + int(noise(-400, 400))
    expected_requests = total_requests
    r1_cpu = 0.38 + noise(-0.02, 0.02)
    r2_login = 0.85 + noise(-0.015, 0.015)
    r3_entropy = 2.5 + noise(-0.08, 0.08)
    r4_rpc = 1.1 + noise(-0.03, 0.03)
    r5_error = 0.02 + noise(-0.003, 0.003)
    latency = 80.0 + noise(-4.0, 4.0)

    if scenario == "MERCH_DROP_SURGE":
        # Massive legitimate traffic surge
        total_requests = 150000 + int(noise(-2000, 2000))
        expected_requests = total_requests
        r1_cpu = 0.74 + noise(-0.01, 0.01)
        r2_login = 0.83 + noise(-0.01, 0.01)
        r3_entropy = 2.4 + noise(-0.04, 0.04)
        r4_rpc = 1.2 + noise(-0.02, 0.02)
        r5_error = 0.035 + noise(-0.004, 0.004)
        latency = 160.0 + noise(-8.0, 8.0)

    elif scenario == "CREDENTIAL_STUFFING":
        # Attack masked within the merch surge
        expected_requests = 150000 + int(noise(-2000, 2000))
        total_requests = expected_requests + 10000 # 10k malicious requests
        r1_cpu = 0.88 + noise(-0.01, 0.01)
        r2_login = 0.18 # Hard crash threshold
        r3_entropy = 1.4 # Hard crash threshold
        r4_rpc = 1.2 + noise(-0.02, 0.02)
        r5_error = 0.125 + noise(-0.005, 0.005)
        latency = 220.0 + noise(-12.0, 12.0)

    elif scenario == "CREDENTIAL_STUFFING_MITIGATED":
        # Causal remediation feedback: botnet blocked
        expected_requests = 150000 + int(noise(-2000, 2000))
        total_requests = expected_requests
        r1_cpu = 0.74 + noise(-0.01, 0.01)
        r2_login = 0.83 + noise(-0.01, 0.01)
        r3_entropy = 2.4 + noise(-0.04, 0.04)
        r4_rpc = 1.2 + noise(-0.02, 0.02)
        r5_error = 0.035 + noise(-0.004, 0.004)
        latency = 160.0 + noise(-8.0, 8.0)

    elif scenario == "RECOVERY":
        # Graceful return to normal parameters after Merch Drop ends
        total_requests = 11000 + int(noise(-400, 400))
        expected_requests = total_requests
        r1_cpu = 0.38 + noise(-0.02, 0.02)
        r2_login = 0.85 + noise(-0.015, 0.015)
        r3_entropy = 2.5 + noise(-0.08, 0.08)
        r4_rpc = 1.1 + noise(-0.03, 0.03)
        r5_error = 0.02 + noise(-0.003, 0.003)
        latency = 80.0 + noise(-4.0, 4.0)

    elif scenario == "RETRY_STORM":
        # Internal configuration fault causing massive RPC cascade loops
        expected_requests = 11000 + int(noise(-400, 400))
        total_requests = expected_requests + 80000 # Amplified loop traffic
        r1_cpu = 0.98 + noise(-0.005, 0.005)
        r2_login = 0.81 + noise(-0.01, 0.01)
        r3_entropy = 2.5 + noise(-0.08, 0.08)
        r4_rpc = 8.5 # High spike
        r5_error = 0.65 + noise(-0.02, 0.02) # Enormous failure rate due to connection timeouts
        latency = 2500.0 # Extreme queuing latency

    elif scenario == "RETRY_STORM_MITIGATED":
        # Configuration rollback restores system health immediately
        total_requests = 11000 + int(noise(-400, 400))
        expected_requests = total_requests
        r1_cpu = 0.38 + noise(-0.02, 0.02)
        r2_login = 0.85 + noise(-0.015, 0.015)
        r3_entropy = 2.5 + noise(-0.08, 0.08)
        r4_rpc = 1.1 + noise(-0.03, 0.03)
        r5_error = 0.02 + noise(-0.003, 0.003)
        latency = 80.0 + noise(-4.0, 4.0)

    # Compute Unexplained Residual
    residual = max(0, total_requests - expected_requests)

    return {
        "tick": tick,
        "scenario": scenario,
        "context": context,
        "health": health,
        "total_requests": total_requests,
        "expected_requests": expected_requests,
        "residual": residual,
        "r1_cpu_utilization": round(r1_cpu, 4),
        "r2_login_success": round(r2_login, 4),
        "r3_entropy": round(r3_entropy, 4),
        "r4_rpc_amplification": round(r4_rpc, 4),
        "r5_error_rate": round(r5_error, 4),
        "p95_latency": round(latency, 2)
    }

def run_inference(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mock ML Inference Engine using strict deterministic state heuristics
    to guarantee crash-free presentation alerts under constraints.
    Returns structured incident RCA reports when anomalies trigger.
    """
    r2 = telemetry["r2_login_success"]
    r3 = telemetry["r3_entropy"]
    r4 = telemetry["r4_rpc_amplification"]

    if r3 < 2.0 and r2 < 0.3:
        return {
            "verdict": "ALERT_CREDENTIAL_STUFFING",
            "probability": 0.94,
            "rca": "Residual isolated to static TTL cohort. Cause: Malicious. Conf: 94%.",
            "recommended_action": "throttle_botnet",
            "action_display": "Throttle Botnet Cohort",
            "rca_report": {
                "incident_id": "INC-2026-8092",
                "incident_title": "Credential Stuffing via Botnet Attack",
                "severity": "CRITICAL",
                "root_cause": "An external botnet is executing brute-force dictionary attacks against the /login endpoint, masked under the high-volume traffic of the Merchandise Drop event.",
                "components_affected": ["edge-gateway", "auth-service", "user-db"],
                "anomalies_detected": [
                    f"Payload entropy dropped to {r3:.2f} (anomaly threshold < 2.0)",
                    f"Login success rate collapsed to {r2*100:.1f}% (anomaly threshold < 30.0%)",
                    f"Unexplained residual traffic surge of {telemetry['residual']:,} requests/minute detected"
                ],
                "trigger_conditions": "r3 < 2.0 AND r2 < 0.3",
                "commit_or_origin": "Origin Signature: Cohort-91 (Static TTL header profile, randomized IPs)",
                "mitigation_plan": "Deploy a targeted rate limiter at the API gateway level to drop packets matching the static TTL signature cohort, protecting authentication database connection pools."
            }
        }
    elif r4 > 5.0:
        return {
            "verdict": "ALERT_INTERNAL_FAULT",
            "probability": 0.89,
            "rca": "RPC cascade localized to payment-service/config.yaml (commit a7f31c2). max_retries=-1. Conf: 89%.",
            "recommended_action": "rollback_config",
            "action_display": "Rollback Configuration",
            "rca_report": {
                "incident_id": "INC-2026-1147",
                "incident_title": "Cascading Downstream RPC Retry Storm",
                "severity": "CRITICAL",
                "root_cause": "An operator config deployment injected an infinite retry policy with zero backoff, amplifying network requests exponentially during a latency event.",
                "components_affected": ["payment-service", "order-service", "edge-gateway"],
                "anomalies_detected": [
                    f"RPC amplification factor spiked to {r4:.2f}x (anomaly threshold > 5.0x)",
                    f"System latency (p95) spiked to {telemetry['p95_latency']:.0f}ms (threshold > 500ms)",
                    f"Global HTTP error rate rose to {telemetry['r5_error_rate']*100:.1f}% (threshold > 10.0%)"
                ],
                "trigger_conditions": "r4 > 5.0",
                "commit_or_origin": "Commit Location: payment-service/config.yaml (commit a7f31c2 by operator@cisco.com)",
                "mitigation_plan": "Rollback configuration settings immediately. Re-apply the timeout baseline of 1500ms with a max_retries limit of 3 and exponential backoff configuration."
            }
        }
    else:
        # Determine suppression message context
        scenario = telemetry["scenario"]
        if scenario in ["NORMAL", "RECOVERY", "CREDENTIAL_STUFFING_MITIGATED", "RETRY_STORM_MITIGATED"]:
            rca_msg = "System operating within normal baseline parameters."
        else:
            rca_msg = "Legitimate load surge detected. All service invariants satisfied."
            
        return {
            "verdict": "SUPPRESS_EXPECTED_EVENT",
            "probability": 1.0,
            "rca": rca_msg,
            "recommended_action": None,
            "action_display": None,
            "rca_report": None
        }

# Global State
class SimulationState:
    def __init__(self):
        self.current_tick: int = 1
        self.mitigation_applied: bool = False
        self.active_mitigations: List[str] = []
        self.history: List[Dict[str, Any]] = []
        
        # Initialize with tick 1 data
        self.initialize_tick_one()

    def reset(self):
        self.current_tick = 1
        self.mitigation_applied = False
        self.active_mitigations = []
        self.history = []
        self.initialize_tick_one()

    def initialize_tick_one(self):
        telemetry = generate_telemetry_data(1, self.active_mitigations)
        inference = run_inference(telemetry)
        telemetry["inference"] = inference
        self.history.append(telemetry)

# Initialize the global state object
state = SimulationState()

# Endpoints
@app.get("/api/state")
def get_state():
    """Returns the current digital twin state and full historical telemetry series."""
    return {
        "current_tick": state.current_tick,
        "mitigation_applied": state.mitigation_applied,
        "active_mitigations": state.active_mitigations,
        "history": state.history
    }

@app.post("/api/step")
def step_simulation():
    """Increments simulation time tick by 1, generates telemetry, runs inference, and saves history."""
    if state.current_tick >= 30:
        return {
            "status": "COMPLETED",
            "message": "Simulation reached maximum tick limit of 30.",
            "state": get_state()
        }
        
    state.current_tick += 1
    new_telemetry = generate_telemetry_data(state.current_tick, state.active_mitigations)
    new_inference = run_inference(new_telemetry)
    new_telemetry["inference"] = new_inference
    
    state.history.append(new_telemetry)
    return get_state()

@app.post("/api/remediate")
def remediate_system(payload: RemediationRequest):
    """
    Action Endpoint. Accepts a remediation action, updates global mitigations,
    and applies causal feedback to force telemetry back to healthy states.
    """
    action = payload.action
    if action not in ["throttle_botnet", "rollback_config"]:
        raise HTTPException(status_code=400, detail="Invalid remediation action.")
        
    state.mitigation_applied = True
    if action not in state.active_mitigations:
        state.active_mitigations.append(action)
        
    # Apply immediate update to the current tick's telemetry in history
    # to show instant visual impact upon mitigation
    cur_idx = state.current_tick - 1
    if 0 <= cur_idx < len(state.history):
        updated_telemetry = generate_telemetry_data(state.current_tick, state.active_mitigations)
        updated_inference = run_inference(updated_telemetry)
        updated_telemetry["inference"] = updated_inference
        state.history[cur_idx] = updated_telemetry

    return {
        "status": "SUCCESS",
        "message": f"Remediation action '{action}' successfully deployed to control plane.",
        "state": get_state()
    }

@app.post("/api/reset")
def reset_simulation():
    """Resets simulator back to Tick 1 and wipes out mitigations/history."""
    state.reset()
    return {
        "status": "SUCCESS",
        "message": "Digital Twin simulator reset to Tick 1 successfully.",
        "state": get_state()
    }
