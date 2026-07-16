from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncio
import json
import os
import yaml
from typing import List, Dict, Any, Optional
from datetime import datetime

from shared.schemas import PublicObservation, DecisionCommit, ActionProposal
from simulator.clock import SimulationClock
from simulator.dynamics.services import SimulationDynamics
from simulator.private.ground_truth import GroundTruthStore

app = FastAPI(title="Context-Aware Observability Digital Twin Simulator")

# Enable CORS for local dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simulator global states
SIM_SEED = 42
SIM_SPEED = 20.0  # 1 real sec = 20 sim sec (3 real sec = 1 sim min)
SIM_MODE = "presentation"

clock: Optional[SimulationClock] = None
dynamics: Optional[SimulationDynamics] = None
truth_store: Optional[GroundTruthStore] = None
observations_history: List[Dict[str, Any]] = []
action_log: List[Dict[str, Any]] = []
decision_commits: List[DecisionCommit] = []
is_running = False
sim_task: Optional[asyncio.Task] = None
websocket_connections: List[WebSocket] = []

def init_simulator(seed: int, speed: float, mode: str):
    global clock, dynamics, truth_store, observations_history, action_log, decision_commits, is_running
    clock = SimulationClock(start_time_str="2026-07-16T20:00:00Z", speed_multiplier=speed)
    dynamics = SimulationDynamics(services_config_path="config/services.yaml", seed=seed)
    truth_store = GroundTruthStore(seed=seed, mode=mode)
    observations_history.clear()
    action_log.clear()
    decision_commits.clear()
    is_running = False

init_simulator(SIM_SEED, SIM_SPEED, SIM_MODE)

# Background tick loop
async def simulator_loop():
    global is_running, clock, dynamics, truth_store, observations_history, websocket_connections
    print("Simulator background loop started.")
    tick_count = 0
    try:
        while is_running:
            # We tick every simulated minute
            # Since speed_multiplier = 20, 1 simulated minute (60 seconds) = 3 real seconds.
            sleep_time = 60.0 / clock.speed_multiplier
            await asyncio.sleep(sleep_time)
            
            sim_time_str = clock.get_simulated_time_str()
            # Calculate the current simulated minute index
            sim_time = clock.get_simulated_time()
            elapsed_seconds = (sim_time - clock.start_time).total_seconds()
            minute = int(elapsed_seconds // 60)
            
            # Fetch private ground truth
            truth = truth_store.get_truth_for_minute(minute)
            
            # Tick the service dynamics
            observation_data = dynamics.tick(minute, truth, sim_time_str)
            observations_history.append(observation_data)
            
            # Broadcast observation to all WebSocket connections
            payload = {
                "type": "observation",
                "timestamp": sim_time_str,
                "minute": minute,
                "observation": observation_data
            }
            # Remove any local datetime or complex types before sending
            serialized_payload = json.loads(json.dumps(payload, default=str))
            
            # Forbidden field audit to prevent indirect leaks to public stream
            FORBIDDEN_TERMS = {"true_cause", "scenario_type", "scenario_order", "attack_active", 
                               "faulty_service", "expected_action", "ground_truth", "next_scenario"}
            text_payload = json.dumps(serialized_payload).lower()
            for term in FORBIDDEN_TERMS:
                if term in text_payload:
                    print(f"WARNING: Forbidden term '{term}' leaked in public observation payload!")
                    # Scrub it or raise error
            
            for ws in list(websocket_connections):
                try:
                    await ws.send_json(serialized_payload)
                except Exception:
                    websocket_connections.remove(ws)
                    
            print(f"Simulated Minute {minute} tick processed at {sim_time_str}.")
            tick_count += 1
            
    except asyncio.CancelledError:
        print("Simulator loop cancelled.")
    except Exception as e:
        print(f"Error in simulator loop: {e}")
        import traceback
        traceback.print_exc()

# ----------------- PRIVATE ADMIN APIs -----------------
@app.post("/admin/simulation/start")
async def admin_start_sim():
    global is_running, sim_task
    if is_running:
        return {"status": "already running"}
    is_running = True
    clock.resume()
    sim_task = asyncio.create_task(simulator_loop())
    return {"status": "started", "speed": clock.speed_multiplier}

@app.post("/admin/simulation/stop")
async def admin_stop_sim():
    global is_running, sim_task
    if not is_running:
        return {"status": "already stopped"}
    is_running = False
    clock.pause()
    if sim_task:
        sim_task.cancel()
    return {"status": "stopped"}

@app.post("/admin/simulation/reset")
async def admin_reset_sim(seed: int = 42, speed: float = 20.0, mode: str = "presentation"):
    global sim_task, is_running
    if is_running:
        is_running = False
        if sim_task:
            sim_task.cancel()
    init_simulator(seed, speed, mode)
    return {"status": "reset", "seed": seed, "speed": speed, "mode": mode}

# Dashboard-friendly aliases (called by app.js)
@app.post("/simulator/start")
async def sim_start(): return await admin_start_sim()

@app.post("/simulator/stop")
async def sim_stop(): return await admin_stop_sim()

@app.post("/simulator/reset")
async def sim_reset(): return await admin_reset_sim()

@app.get("/admin/ground-truth")
async def admin_get_ground_truth():
    if not truth_store:
        raise HTTPException(status_code=400, detail="Simulator not initialized")
    timeline_with_truths = []
    for entry in truth_store.timeline:
        sc_truth = truth_store.scenarios.get(entry["scenario"]) if entry["scenario"] else None
        timeline_with_truths.append({
            "start": entry["start"],
            "end": entry["end"],
            "scenario": entry["scenario"],
            "truth": sc_truth.dict() if sc_truth else None
        })
    return {
        "seed": truth_store.seed,
        "mode": truth_store.mode,
        "timeline": timeline_with_truths,
        "active_faults": dynamics.circuit_breakers
    }

# ----------------- PUBLIC AGENT APIs -----------------
@app.get("/agent/observations/latest")
async def agent_get_latest_observation():
    if not observations_history:
        return {
            "timestamp": clock.get_simulated_time_str(),
            "tick_index": 0,
            "total_rps": 0,
            "retry_amplification": 1.0,
            "explained_fraction": 1.0,
            "validated_viewers": 0,
            "services": {},
            "business_context": None,
            "service_metrics": [],
            "network_flow_windows": [],
            "logs": [],
            "traces": [],
            "deployment_changes": [],
            "configuration_snapshots": []
        }
    obs = observations_history[-1]
    # Enrich with tick index and quick-access fields for the dashboard
    tick_index = len(observations_history) - 1
    enriched = dict(obs)
    enriched.setdefault("tick_index", tick_index)
    # Build flat services dict if not already present
    if "services" not in enriched:
        svc_dict = {}
        for metric in enriched.get("service_metrics", []):
            svc_name = metric.get("service") if isinstance(metric, dict) else getattr(metric, "service", None)
            if svc_name:
                req = metric.get("requests") if isinstance(metric, dict) else getattr(metric, "requests", 0)
                errs = metric.get("server_errors") if isinstance(metric, dict) else getattr(metric, "server_errors", 0)
                p99  = metric.get("p95_latency_ms") if isinstance(metric, dict) else getattr(metric, "p95_latency_ms", 0)
                retries = metric.get("retries") if isinstance(metric, dict) else getattr(metric, "retries", 0)
                svc_dict[svc_name] = {
                    "request_rate": req,
                    "error_rate": round(errs / max(req, 1), 4),
                    "p99_latency_ms": p99,
                    "retry_rate": round(retries / max(req, 1), 4),
                }
        enriched["services"] = svc_dict
    if "total_rps" not in enriched:
        enriched["total_rps"] = sum(
            v.get("request_rate", 0) for v in enriched["services"].values()
        )
    enriched.setdefault("explained_fraction", 0.85)
    enriched.setdefault("retry_amplification", 1.0)
    enriched.setdefault("validated_viewers",
        enriched.get("business_context", {}) and
        (enriched["business_context"].get("validated_viewers") if isinstance(enriched["business_context"], dict) else 0) or 0
    )
    return json.loads(json.dumps(enriched, default=str))

@app.get("/agent/observations")
async def agent_get_all_observations():
    return observations_history

@app.get("/agent/evidence/logs")
async def agent_get_logs(limit: int = 100):
    logs = []
    for obs in reversed(observations_history):
        logs.extend(obs.get("logs", []))
        if len(logs) >= limit:
            break
    return logs[:limit]

@app.get("/agent/evidence/traces")
async def agent_get_traces(limit: int = 100):
    traces = []
    for obs in reversed(observations_history):
        traces.extend(obs.get("traces", []))
        if len(traces) >= limit:
            break
    return traces[:limit]

@app.get("/agent/evidence/deployments")
async def agent_get_deployments():
    # Only return deployment metadata available up to latest tick
    if not observations_history:
        return []
    return observations_history[-1].get("deployment_changes", [])

@app.get("/agent/evidence/config/{service}")
async def agent_get_config(service: str):
    if not observations_history:
        raise HTTPException(status_code=404, detail="No observations recorded yet")
    configs = observations_history[-1].get("configuration_snapshots", [])
    for cfg in configs:
        # cfg can be ConfigurationSnapshot or dict
        cfg_name = cfg.service if hasattr(cfg, 'service') else cfg.get('service')
        cfg_val = cfg.config if hasattr(cfg, 'config') else cfg.get('config')
        if cfg_name == service:
            return cfg_val
    raise HTTPException(status_code=404, detail=f"Configuration for service {service} not found")

@app.post("/agent/actions/propose")
async def agent_propose_action(action: ActionProposal):
    # Propose an action for policy approval
    # In this digital twin, we save proposal and then it triggers simulator change if approved
    # If the policy does not require approval, we apply it immediately.
    action_dict = action.dict()
    # Check if policy requires approval
    with open("config/policy.yaml", 'r') as f:
        policies = yaml.safe_load(f)["policies"]
    
    policy = policies.get(action.action_type, {"requires_approval": True})
    
    if not policy["requires_approval"]:
        # Execute immediately
        action_dict["status"] = "executed"
        dynamics.apply_action(action.action_type, action.target_service, action.parameters)
        action_log.append(action_dict)
        return {"status": "executed", "action_id": action.action_id}
    else:
        # Needs human approval (via dashboard)
        action_dict["status"] = "proposed"
        action_log.append(action_dict)
        
        # Broadcast proposal to dashboard WebSocket
        proposal_payload = {
            "type": "action_proposal",
            "action": action_dict
        }
        for ws in list(websocket_connections):
            try:
                await ws.send_json(proposal_payload)
            except Exception:
                websocket_connections.remove(ws)
                
        return {"status": "proposed", "action_id": action.action_id}

@app.post("/agent/decisions/commit")
async def agent_commit_decision(decision: DecisionCommit):
    decision_commits.append(decision)
    decision_payload = {
        "type": "decision_commit",
        "decision": decision.dict()
    }
    for ws in list(websocket_connections):
        try:
            await ws.send_json(decision_payload)
        except Exception:
            websocket_connections.remove(ws)
    return {"status": "committed", "decision_id": decision.decision_id}

@app.get("/agent/decisions")
async def agent_get_decisions():
    """Return all committed agent decisions (for dashboard polling)."""
    return {"decisions": [d.dict() for d in decision_commits]}

# ----------------- DASHBOARD & APPROVAL APIs -----------------
@app.get("/dashboard/actions")
async def get_dashboard_actions():
    return action_log

@app.get("/dashboard/decisions")
async def get_dashboard_decisions():
    return [d.dict() for d in decision_commits]

@app.post("/approvals/{action_id}/approve")
async def approve_action(action_id: str):
    global action_log, dynamics
    for action in action_log:
        if action["action_id"] == action_id:
            if action["status"] != "proposed":
                raise HTTPException(status_code=400, detail="Action is not in proposed state")
            action["status"] = "approved"
            dynamics.apply_action(action["action_type"], action["target_service"], action["parameters"])
            action["status"] = "executed"
            broadcast_payload = {"type": "action_status", "action_id": action_id, "status": "executed"}
            for ws in list(websocket_connections):
                try:
                    await ws.send_json(broadcast_payload)
                except Exception:
                    websocket_connections.remove(ws)
            return {"status": "executed", "action_id": action_id}
    raise HTTPException(status_code=404, detail="Action proposal not found")

# Dashboard app.js calls this URL path for action approval
@app.post("/agent/actions/{action_id}/approve")
async def agent_approve_action(action_id: str):
    """Alias for /approvals/{action_id}/approve used by dashboard."""
    return await approve_action(action_id)

@app.post("/approvals/{action_id}/reject")
async def reject_action(action_id: str):
    global action_log
    for action in action_log:
        if action["action_id"] == action_id:
            if action["status"] != "proposed":
                raise HTTPException(status_code=400, detail="Action is not in proposed state")
            action["status"] = "rejected"
            return {"status": "rejected", "action_id": action_id}
    raise HTTPException(status_code=404, detail="Action proposal not found")

@app.websocket("/dashboard/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_connections.append(websocket)
    print(f"New websocket connection. Active: {len(websocket_connections)}")
    try:
        # Keep connection open
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_connections.remove(websocket)
        print("Websocket disconnected.")

# Mount static folder for dashboard if exists
if os.path.exists("dashboard/static"):
    app.mount("/", StaticFiles(directory="dashboard/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
