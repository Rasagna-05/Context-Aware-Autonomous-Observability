import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from shared.schemas import ActionProposal, DecisionCommit


class PolicySelector:
    def __init__(self):
        self.risk_levels = {
            "scale": "low",
            "rate_limit": "medium",
            "restart": "medium",
            "circuit_breaker": "medium",
            "config_patch": "high",
            "rollback": "high"
        }

    def select_actions(self, verdict: str, rca_results: Dict[str, Any], timestamp: str) -> List[ActionProposal]:
        """
        Selects remediation actions appropriate for the root cause and verdict.
        Each action carries a plain-language rationale and blast-radius estimate
        so the dashboard Response & Approval panel can render meaningful UI.
        """
        actions: List[ActionProposal] = []

        if verdict == "external_attack":
            actions.append(ActionProposal(
                action_id=f"act-{uuid.uuid4().hex[:6]}",
                action_type="rate_limit",
                target_service="identity-service",
                risk_level=self.risk_levels["rate_limit"],
                confidence=0.95,
                parameters={
                    "predicate": {
                        "cohort_id": "cohort-91",
                        "invalid_credentials_only": True
                    },
                    "limit_rate_per_sec": 10
                },
                reason="Throttle malicious credential-stuffing traffic while preserving fans.",
                rationale=(
                    "Cohort-91 is generating credential-stuffing requests at 87 req/s with a "
                    "0.3% success rate — a classic bot signature. Selective rate-limit to 10 req/s "
                    "will eliminate 94% of malicious load while fans (cohort-10, cohort-22) are "
                    "unaffected. Rule expires automatically after 15 minutes."
                ),
                description="Selective rate-limit on cohort-91 — 10 req/s cap",
                blast_radius="Minimal — only cohort-91 throttled, fans unaffected",
                status="proposed",
                created_at=timestamp
            ))

            actions.append(ActionProposal(
                action_id=f"act-{uuid.uuid4().hex[:6]}",
                action_type="scale",
                target_service="identity-service",
                risk_level=self.risk_levels["scale"],
                confidence=0.80,
                parameters={"replicas": 2},
                reason="Proactive scaling to handle legitimate user login volume.",
                rationale=(
                    "Even after throttling bots, game-day login traffic remains elevated. "
                    "Adding one replica ensures P99 latency stays under 400 ms for real users "
                    "throughout the match. Scale-in will trigger automatically when traffic drops."
                ),
                description="Add 1 replica to identity-service (2 → 3 pods)",
                blast_radius="None — additive capacity change, zero downtime",
                status="proposed",
                created_at=timestamp
            ))

        elif verdict == "code_config_fault":
            actions.append(ActionProposal(
                action_id=f"act-{uuid.uuid4().hex[:6]}",
                action_type="config_patch",
                target_service="payment-service",
                risk_level=self.risk_levels["config_patch"],
                confidence=0.95,
                parameters={
                    "config": {
                        "payment": {
                            "timeout_ms": 1500,
                            "max_retries": 3,
                            "backoff_ms": 250,
                            "circuit_breaker_enabled": True
                        }
                    },
                    "timestamp": timestamp
                },
                reason="Rollback payment timeouts to 1500 ms, cap retries at 3 with backoff, enable circuit breaker.",
                rationale=(
                    "Deploy 3f8a1c2 set timeout_ms=150 (was 5000). This caused a retry storm: "
                    "each upstream timeout triggers 5 retries × 3 downstream hops = 15x amplification. "
                    "Patching timeout_ms back to 1500 ms and enabling the circuit breaker will "
                    "stop the retry cascade within 2 ticks. No data or session impact expected."
                ),
                description="Patch payment-service timeout_ms: 150 → 1500, enable circuit breaker",
                blast_radius="Low — single service config; rollback takes effect on next request",
                status="proposed",
                created_at=timestamp
            ))

        elif verdict == "operational_fault":
            actions.append(ActionProposal(
                action_id=f"act-{uuid.uuid4().hex[:6]}",
                action_type="restart",
                target_service="identity-service",
                risk_level=self.risk_levels["restart"],
                confidence=0.90,
                parameters={},
                reason="Rolling restart of identity-service to clear session cache memory leaks.",
                rationale=(
                    "Memory utilisation on identity-service has grown 3.4x over 8 minutes without "
                    "a corresponding traffic increase — classic sign of a session-cache leak. "
                    "A rolling restart (one pod at a time) will clear heap without dropping active sessions, "
                    "since the load-balancer will route to healthy pods during the restart cycle."
                ),
                description="Rolling restart — identity-service (pod-by-pod, ~90s total)",
                blast_radius="Low — rolling restart; active sessions preserved by load-balancer",
                status="proposed",
                created_at=timestamp
            ))

        elif verdict == "expected_event":
            actions.append(ActionProposal(
                action_id=f"act-{uuid.uuid4().hex[:6]}",
                action_type="scale",
                target_service="merchandise-service",
                risk_level=self.risk_levels["scale"],
                confidence=0.85,
                parameters={"replicas": 1},
                reason="Scale up merchandise service to support incoming merchandise drop surge.",
                rationale=(
                    "The game clock shows 75:42 — the match is approaching full-time. "
                    "Historical data shows merchandise traffic spikes 4–8x in the final 10 minutes. "
                    "Pre-scaling now (before the spike) avoids cold-start latency under load."
                ),
                description="Predictive scale: merchandise-service +1 replica ahead of FT surge",
                blast_radius="None — additive capacity, no service interruption",
                status="proposed",
                created_at=timestamp
            ))

        return actions
