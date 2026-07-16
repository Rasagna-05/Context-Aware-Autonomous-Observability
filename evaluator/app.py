from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json
from typing import Dict, Any, List, Optional

app = FastAPI(title="Context-Aware Autonomous Observability Evaluator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "healthy", "service": "evaluator"}

SIMULATOR_URL = "http://localhost:8000"

FORBIDDEN_TERMS = {
    "true_cause", "scenario_type", "scenario_order", "attack_active",
    "faulty_service", "expected_action", "ground_truth", "next_scenario"
}

def check_leakage(payload: dict) -> List[str]:
    """
    Scans a payload for any leaked forbidden terms.
    """
    text = json.dumps(payload).lower()
    leaks = []
    for term in FORBIDDEN_TERMS:
        if term in text:
            leaks.append(term)
    return leaks

@app.get("/evaluator/leakage-check")
async def run_leakage_check():
    """
    Polls all observations from the simulator and checks if they leaked any forbidden ground truth terms.
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{SIMULATOR_URL}/agent/observations")
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch observations")
            
            observations = resp.json()
            leaks_found = []
            for idx, obs in enumerate(observations):
                leaks = check_leakage(obs)
                if leaks:
                    leaks_found.append({
                        "observation_index": idx,
                        "timestamp": obs.get("timestamp"),
                        "leaked_terms": leaks
                    })
            
            return {
                "leakage_audit_passed": len(leaks_found) == 0,
                "leaks_count": len(leaks_found),
                "leaks": leaks_found
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/evaluator/run-summary")
async def get_run_summary():
    """
    Compares committed decisions against simulator ground truth to evaluate performance.
    """
    async with httpx.AsyncClient() as client:
        try:
            # 1. Fetch decisions
            dec_resp = await client.get(f"{SIMULATOR_URL}/dashboard/decisions")
            if dec_resp.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch decisions")
            decisions = dec_resp.json()
            
            # 2. Fetch ground truth
            gt_resp = await client.get(f"{SIMULATOR_URL}/admin/ground-truth")
            if gt_resp.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch ground truth")
            gt_data = gt_resp.json()
            gt_timeline = gt_data.get("timeline", [])
            
            # 3. Score each decision
            scored_decisions = []
            correct_classifications = 0
            correct_rca = 0
            
            for dec in decisions:
                timestamp = dec.get("timestamp")
                # Parse hour/minute to compare with ground truth intervals
                # Format: 2026-07-16T20:00:00Z
                dt = datetime_from_str(timestamp)
                start_dt = datetime_from_str("2026-07-16T20:00:00Z")
                elapsed_minutes = int((dt - start_dt).total_seconds() // 60)
                
                # Find matching scenario
                matched_scenario = None
                for entry in gt_timeline:
                    if entry["start"] <= elapsed_minutes < entry["end"]:
                        matched_scenario = entry
                        break
                
                expected_cause = "expected_event"
                expected_service = None
                expected_artifact = None
                
                if matched_scenario and matched_scenario.get("truth"):
                    truth = matched_scenario["truth"]
                    expected_cause = truth.get("cause")
                    expected_service = truth.get("origin_service")
                    expected_artifact = truth.get("faulty_artifact")
                
                # Compare verdict
                verdict = dec.get("verdict")
                # Normalize mapping (scenario retry_storm maps to code_config_fault)
                verdict_is_correct = False
                if expected_cause == "expected_event" and verdict == "expected_event":
                    verdict_is_correct = True
                elif expected_cause == "retry_storm" and verdict == "code_config_fault":
                    verdict_is_correct = True
                elif expected_cause == "credential_stuffing" and verdict == "external_attack":
                    verdict_is_correct = True
                elif expected_cause == "memory_leak" and verdict == "operational_fault":
                    verdict_is_correct = True
                
                if verdict_is_correct:
                    correct_classifications += 1
                    
                # Compare RCA
                rca_is_correct = False
                if expected_cause in ["expected_event", "credential_stuffing"]:
                    rca_is_correct = True # no internal file to localize
                elif expected_cause == "retry_storm":
                    # Check if localized service and file match
                    rca_is_correct = (dec.get("faulty_service") == expected_service and 
                                      dec.get("faulty_artifact") == expected_artifact)
                elif expected_cause == "memory_leak":
                    rca_is_correct = (dec.get("faulty_service") == expected_service and 
                                      dec.get("faulty_artifact") == expected_artifact)
                    
                if rca_is_correct:
                    correct_rca += 1
                    
                scored_decisions.append({
                    "timestamp": timestamp,
                    "elapsed_minutes": elapsed_minutes,
                    "expected_cause": expected_cause,
                    "agent_verdict": verdict,
                    "verdict_correct": verdict_is_correct,
                    "expected_faulty_service": expected_service,
                    "agent_faulty_service": dec.get("faulty_service"),
                    "expected_faulty_artifact": expected_artifact,
                    "agent_faulty_artifact": dec.get("faulty_artifact"),
                    "rca_correct": rca_is_correct,
                    "likely_commit": dec.get("likely_commit")
                })
                
            total_decisions = len(decisions)
            classification_accuracy = (correct_classifications / total_decisions) if total_decisions > 0 else 1.0
            rca_accuracy = (correct_rca / total_decisions) if total_decisions > 0 else 1.0
            
            return {
                "total_decisions_evaluated": total_decisions,
                "classification_accuracy": classification_accuracy,
                "rca_accuracy": rca_accuracy,
                "evaluations": scored_decisions
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

def datetime_from_str(s: str):
    from datetime import datetime
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
