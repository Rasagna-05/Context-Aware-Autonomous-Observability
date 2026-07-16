import numpy as np
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ScenarioTruth(BaseModel):
    scenario_id: str
    cause: str
    origin_service: Optional[str] = None
    faulty_artifact: Optional[str] = None
    faulty_keys: List[str] = []
    intensity: float = 1.0
    correct_actions: List[str] = []
    description: str

class GroundTruthStore:
    def __init__(self, seed: int = 42, mode: str = "presentation"):
        self.seed = seed
        self.mode = mode
        self.rng = np.random.default_rng(seed)
        self.active_faults = {}
        self.active_attacks = {}
        
        # Scenario definitions
        self.scenarios = {
            "retry_storm": ScenarioTruth(
                scenario_id="retry_storm",
                cause="retry_storm",
                origin_service="payment-service",
                faulty_artifact="services/payment-service/config.yaml",
                faulty_keys=["payment.timeout_ms", "payment.max_retries", "payment.backoff_ms"],
                correct_actions=["config_patch", "rollback"],
                description="Legitimate load exposes misconfigured unlimited retries and short timeouts."
            ),
            "merch_drop_clean": ScenarioTruth(
                scenario_id="merch_drop_clean",
                cause="expected_event",
                description="Large legitimate surge in merchandise sales with correct configuration."
            ),
            "credential_stuffing": ScenarioTruth(
                scenario_id="credential_stuffing",
                cause="credential_stuffing",
                correct_actions=["rate_limit"],
                description="Credential stuffing attack targeted at /login endpoint."
            ),
            "memory_leak": ScenarioTruth(
                scenario_id="memory_leak",
                cause="memory_leak",
                origin_service="identity-service",
                faulty_artifact="services/identity-service/app.py",
                correct_actions=["restart"],
                description="Memory leak in identity service session caching."
            )
        }
        
        # Set up timeline based on mode
        self.timeline = []
        self.setup_timeline()

    def setup_timeline(self):
        if self.mode == "presentation":
            # Compressed 5-minute demo timeline (at 20x speed = 3 real-sec per sim-minute)
            # Each scenario gets ~3 ticks = ~9 real seconds to show clear classification
            # Total: 10 ticks = ~30 real seconds visible change, full demo in under 5 mins
            self.timeline = [
                {"start": 0,  "end": 2,  "scenario": None},                  # T0-T1:  Baseline (healthy)
                {"start": 2,  "end": 5,  "scenario": "retry_storm"},         # T2-T4:  Config fault (retry storm)
                {"start": 5,  "end": 7,  "scenario": "merch_drop_clean"},    # T5-T6:  Clean game-day surge
                {"start": 7,  "end": 10, "scenario": "credential_stuffing"}, # T7-T9:  Attack overlay
            ]
        else:
            # Randomized order for validation seeds
            scenarios_pool = ["retry_storm", "merch_drop_clean", "credential_stuffing", "memory_leak"]
            self.rng.shuffle(scenarios_pool)
            current_time = 0
            self.timeline.append({"start": 0, "end": 2, "scenario": None})
            current_time = 2
            for sc in scenarios_pool:
                dur = int(self.rng.integers(3, 5))
                self.timeline.append({"start": current_time, "end": current_time + dur, "scenario": sc})
                current_time += dur

    def get_truth_for_minute(self, minute: int) -> Optional[ScenarioTruth]:
        for entry in self.timeline:
            if entry["start"] <= minute < entry["end"]:
                sc_name = entry["scenario"]
                if sc_name:
                    return self.scenarios[sc_name]
        return None
