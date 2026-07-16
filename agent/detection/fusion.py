from typing import Dict, Any, List, Optional
from shared.schemas import PublicObservation
from agent.baseline.residuals import ResidualEngine
from agent.features.ratios import DiagnosticIndicators


class DetectionFusion:
    def __init__(self):
        self.residual_engine = ResidualEngine()
        self.state_history: List[Dict[str, Any]] = []
        self.persistence_threshold = 2  # Require 2 consecutive ticks for incident

    def process_observation(self, obs: PublicObservation) -> Dict[str, Any]:
        """
        Runs all detector branches and fuses their outputs.
        Uses only ratio-based numerical indicators — never peeks at scenario labels.
        """
        metrics = obs.service_metrics
        flows   = obs.network_flow_windows
        context = obs.business_context

        # ── 1. Calculate diagnostic ratio indicators ──────────────────────────
        ratios = DiagnosticIndicators.calculate_ratios(metrics, flows)

        # ── 2. Traffic decomposition (identity-service = login endpoint) ──────
        def svc_name(m):
            return m.get("service") if isinstance(m, dict) else m.service

        login_metrics = next((m for m in metrics if svc_name(m) == "identity-service"), None)
        if isinstance(login_metrics, dict):
            login_observed = login_metrics.get("requests", 0)
        else:
            login_observed = login_metrics.requests if login_metrics else 0

        login_med, login_exp, login_res = self.residual_engine.decompose(
            "identity-service", login_observed, context
        )

        merch_metrics = next((m for m in metrics if svc_name(m) == "merchandise-service"), None)
        if isinstance(merch_metrics, dict):
            merch_observed = merch_metrics.get("requests", 0)
        else:
            merch_observed = merch_metrics.requests if merch_metrics else 0

        merch_med, merch_exp, merch_res = self.residual_engine.decompose(
            "merchandise-service", merch_observed, context
        )

        # ── 3. ATTACK BRANCH: Credential stuffing detector ─────────────────────
        # Signals: high invalid_credential_rate + flow with low TTL + concentrated source
        id_ratios = ratios.get("identity-service", {})
        invalid_cred_rate  = id_ratios.get("invalid_credential_rate", 0.0)
        req_per_session    = id_ratios.get("req_per_session", 1.0)

        # Flow-level attack signal: look for any cohort with suspicious flow pattern
        # (low TTL dttl < 64, high rate, asymmetric packet ratio)
        attack_flow_score = 0.0
        flow_ratios = ratios.get("_flows", {})
        for cohort_id, fr in flow_ratios.items():
            # Attack signature: high send rate, asymmetric bytes, packet loss, low inter-packet time
            rate        = fr.get("rate", 0.0)
            pkt_ratio   = fr.get("packet_ratio", 1.0)    # Spkts/Dpkts >> 1 means many unanswered requests
            loss_rate   = fr.get("loss_rate", 0.0)
            sload       = fr.get("sload", 0.0)
            # High rate + asymmetric (more sent than received) + some loss = attack signature
            if rate > 500 and pkt_ratio > 1.3 and loss_rate > 0.0:
                # Score based on severity
                attack_flow_score = max(attack_flow_score, min(1.0, rate / 7000.0 + pkt_ratio * 0.1))

        # Combine: attack requires BOTH invalid credential signal AND suspicious flow
        attack_score = 0.0
        if invalid_cred_rate > 0.60 and attack_flow_score > 0.30:
            attack_score = min(0.97, (invalid_cred_rate * 0.6) + (attack_flow_score * 0.4))
        elif invalid_cred_rate > 0.80:
            # Even without flow data, very high invalid cred rate is suspicious
            attack_score = min(0.85, invalid_cred_rate * 0.9)

        # ── 4. FAULT BRANCH: Retry storm / config fault detector ───────────────
        # Signals: high retry_amplification on payment-service + timeout rate + recent deploy
        pay_ratios          = ratios.get("payment-service", {})
        retry_amplification = pay_ratios.get("retry_amplification", 0.0)  # retries/requests
        timeout_rate        = pay_ratios.get("timeout_rate", 0.0)          # timeouts/requests
        pay_error_rate      = pay_ratios.get("server_error_rate", 0.0)

        retry_storm_score = 0.0
        # retry_amplification > 1 means more retries than requests (storm condition)
        if retry_amplification > 2.0:
            retry_storm_score = min(0.97, 0.7 + retry_amplification / 30.0)
        elif retry_amplification > 0.5 or (timeout_rate > 0.25 and pay_error_rate > 0.1):
            retry_storm_score = 0.60
        elif timeout_rate > 0.10:
            retry_storm_score = 0.35

        # ── 5. OPERATIONAL FAULT BRANCH: Memory leak detector ──────────────────
        memory_leak_score = 0.0
        id_mem = None
        for m in metrics:
            svc_name = m.get("service") if isinstance(m, dict) else m.service
            if svc_name == "identity-service":
                id_mem = m.get("memory_mb") if isinstance(m, dict) else m.memory_mb
                break

        if id_mem is not None:
            past_memories = [h.get("id_memory") for h in self.state_history[-5:]
                             if h.get("id_memory") is not None]
            if len(past_memories) >= 3 and id_mem > 2500.0:
                # All past values increasing monotonically = leak
                if all(id_mem > pm for pm in past_memories):
                    memory_leak_score = 0.85

        # ── 6. Update sliding window history ───────────────────────────────────
        self.state_history.append({
            "timestamp":         obs.timestamp,
            "id_memory":         id_mem,
            "retry_storm_score": retry_storm_score,
            "attack_score":      attack_score,
        })
        if len(self.state_history) > 10:
            self.state_history.pop(0)

        # ── 7. Persistence check (require N consecutive ticks) ─────────────────
        consecutive_fault  = 0
        consecutive_attack = 0
        for h in reversed(self.state_history):
            if h["retry_storm_score"] > 0.50:
                consecutive_fault += 1
            else:
                break
        for h in reversed(self.state_history):
            if h["attack_score"] > 0.50:
                consecutive_attack += 1
            else:
                break

        # ── 8. Fusion & Verdict ────────────────────────────────────────────────
        verdict          = "expected_event"
        confidence       = 1.0
        incident_active  = False

        # Priority: attack+fault > attack > fault > operational > event
        fault_confirmed  = (retry_storm_score > 0.65 and consecutive_fault  >= self.persistence_threshold)
        attack_confirmed = (attack_score      > 0.65 and consecutive_attack >= self.persistence_threshold)

        if attack_confirmed and fault_confirmed:
            verdict         = "attack_and_fault"
            confidence      = max(attack_score, retry_storm_score)
            incident_active = True
        elif attack_confirmed:
            verdict         = "external_attack"
            confidence      = attack_score
            incident_active = True
        elif fault_confirmed:
            verdict         = "code_config_fault"
            confidence      = retry_storm_score
            incident_active = True
        elif memory_leak_score > 0.70:
            verdict         = "operational_fault"
            confidence      = memory_leak_score
            incident_active = True
        elif login_res > 1000 or merch_res > 1000:
            verdict         = "unknown"
            confidence      = 0.50
            incident_active = True
        # else stays "expected_event" with confidence 1.0

        return {
            "incident_active":      incident_active,
            "verdict":              verdict,
            "confidence":           confidence,
            "scores": {
                "expected_event":   1.0 - max(attack_score, retry_storm_score, memory_leak_score),
                "external_attack":  attack_score,
                "code_config_fault": retry_storm_score,
                "operational_fault": memory_leak_score,
            },
            "login_residual":       login_res,
            "merch_residual":       merch_res,
            "retry_amplification":  retry_amplification,
            "invalid_cred_rate":    invalid_cred_rate,
            "consecutive_fault":    consecutive_fault,
            "consecutive_attack":   consecutive_attack,
        }
