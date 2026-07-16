from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import httpx
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from shared.schemas import PublicObservation, DecisionCommit, ActionProposal
from agent.detection.fusion import DetectionFusion
from agent.rca.scorer import RCAScorer
from agent.policy.selector import PolicySelector

app = FastAPI(title="Context-Aware Autonomous Observability Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "healthy", "service": "agent"}

# Agent state
detector = DetectionFusion()
rca_scorer = RCAScorer()
policy_selector = PolicySelector()

last_processed_timestamp: Optional[str] = None
is_running = False
polling_task: Optional[asyncio.Task] = None
SIMULATOR_URL = "http://localhost:8000"

async def run_inference_cycle(obs_dict: Dict[str, Any]):
    global last_processed_timestamp

    timestamp = obs_dict.get("timestamp")
    if not timestamp or timestamp == last_processed_timestamp:
        return

    print(f"Agent starting inference cycle for tick {timestamp}...")

    # Build a lightweight observation wrapper that engines can query
    # Engines now accept dicts directly (via _get() helpers in ratios.py)
    # We still need a PublicObservation for the RCA scorer's deployment_changes check
    try:
        # Try to build the Pydantic model — will succeed when all fields are clean dicts
        obs = PublicObservation(
            timestamp=timestamp,
            business_context=obs_dict.get("business_context"),
            service_metrics=obs_dict.get("service_metrics", []),
            network_flow_windows=obs_dict.get("network_flow_windows", []),
            logs=obs_dict.get("logs", []),
            traces=obs_dict.get("traces", []),
            deployment_changes=obs_dict.get("deployment_changes", []),
            configuration_snapshots=obs_dict.get("configuration_snapshots", []),
        )
    except Exception as e:
        print(f"Warning: Could not parse full PublicObservation: {e}. Using raw dict.")
        # Fallback: create a minimal object so engines can still run
        obs = type("Obs", (), {
            "timestamp": timestamp,
            "business_context": obs_dict.get("business_context"),
            "service_metrics": obs_dict.get("service_metrics", []),
            "network_flow_windows": obs_dict.get("network_flow_windows", []),
            "logs": obs_dict.get("logs", []),
            "traces": obs_dict.get("traces", []),
            "deployment_changes": obs_dict.get("deployment_changes", []),
            "configuration_snapshots": obs_dict.get("configuration_snapshots", []),
        })()

    # 1. Detection & Classification
    results = detector.process_observation(obs)
    verdict    = results["verdict"]
    confidence = results["confidence"]

    # 2. Root-Cause Analysis
    rca_results = rca_scorer.run_rca(obs, verdict)

    # 3. Policy & Remediation Selection
    proposed_actions = policy_selector.select_actions(verdict, rca_results, timestamp)

    # 4. Construct Decision Commit
    decision = DecisionCommit(
        decision_id=f"dec-{uuid.uuid4().hex[:6]}",
        timestamp=timestamp,
        incident_active=results["incident_active"],
        verdict=verdict,
        confidence=confidence,
        hypotheses_scores=rca_results["hypotheses_scores"],
        evidence_chain=rca_results["evidence_chain"],
        primary_root_cause=rca_results["primary_root_cause"],
        faulty_service=rca_results["faulty_service"],
        faulty_artifact=rca_results["faulty_artifact"],
        faulty_keys=rca_results["faulty_keys"],
        likely_commit=rca_results["likely_commit"],
        proposed_actions=proposed_actions
    )

    # 5. Send decisions and actions back to simulator
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{SIMULATOR_URL}/agent/decisions/commit", json=decision.dict())
            print(f"Decision committed: {resp.status_code} | verdict={verdict} | conf={confidence:.2f}")
        except Exception as e:
            print(f"Failed to commit decision: {e}")

        for act in proposed_actions:
            try:
                resp = await client.post(f"{SIMULATOR_URL}/agent/actions/propose", json=act.dict())
                print(f"Action proposed: {act.action_type} -> {resp.status_code}")
            except Exception as e:
                print(f"Failed to propose action {act.action_type}: {e}")

    last_processed_timestamp = timestamp
    print(f"Agent inference completed | tick={timestamp} | verdict={verdict} | confidence={confidence:.2f}")


async def polling_loop():
    global is_running
    print("Agent polling loop started.")
    async with httpx.AsyncClient() as client:
        while is_running:
            try:
                # Poll latest observation
                resp = await client.get(f"{SIMULATOR_URL}/agent/observations/latest")
                if resp.status_code == 200:
                    obs_data = resp.json()
                    if obs_data and obs_data.get("timestamp"):
                        await run_inference_cycle(obs_data)
            except Exception as e:
                print(f"Error connecting to simulator: {e}")
                
            # Poll every 1 second (fast enough to catch every tick)
            await asyncio.sleep(1.0)

@app.post("/agent/start")
async def start_agent():
    global is_running, polling_task
    if is_running:
        return {"status": "agent already running"}
    is_running = True
    polling_task = asyncio.create_task(polling_loop())
    return {"status": "agent started"}

@app.post("/agent/stop")
async def stop_agent():
    global is_running, polling_task
    if not is_running:
        return {"status": "agent already stopped"}
    is_running = False
    if polling_task:
        polling_task.cancel()
    return {"status": "agent stopped"}

@app.get("/agent/status")
async def get_status():
    return {
        "is_running": is_running,
        "last_processed_timestamp": last_processed_timestamp
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
