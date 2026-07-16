import yaml
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
from shared.schemas import ServiceMetricWindow, FlowWindow, TraceSpan, LogMessage, ConfigurationSnapshot, BusinessContext
import uuid

class ServiceState:
    def __init__(self, name: str, info: Dict[str, Any]):
        self.name = name
        self.replicas = info["replicas"]
        self.base_replicas = info["replicas"]
        self.capacity_per_replica = info["capacity_per_replica"]
        self.base_latency_ms = info["base_latency_ms"]
        self.dependencies = info["dependencies"]
        self.config = info.get("config", {}).copy()
        
        # Dynamic state
        self.queue_depth = 0
        self.cpu_percent = 10.0
        self.memory_mb = 500.0
        self.leak_accumulated_mb = 0.0
        
        # Reset per step
        self.last_metrics: Dict[str, Any] = {}

class SimulationDynamics:
    def __init__(self, services_config_path: str, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.services: Dict[str, ServiceState] = {}
        self.load_config(services_config_path)
        
        # Track active remediations
        self.rate_limits: List[Dict[str, Any]] = []
        self.circuit_breakers: Dict[str, bool] = {}
        self.deployment_history: List[Dict[str, Any]] = [
            # Some harmless distractor commits
            {
                "service": "identity-service",
                "commit": "ef8291a",
                "deployed_at": "2026-07-16T19:30:00Z",
                "changed_files": ["services/identity-service/app.py"],
                "changed_keys": ["session_cache_ttl_seconds"]
            },
            {
                "service": "streaming-service",
                "commit": "bc5190b",
                "deployed_at": "2026-07-16T19:45:00Z",
                "changed_files": ["services/streaming-service/session.py"],
                "changed_keys": ["heartbeat_interval"]
            }
        ]
        
        # In Scenario A, this will contain the faulty commit at t=2
        self.faulty_commit_deployed = False

    def load_config(self, path: str):
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        for name, info in data["services"].items():
            self.services[name] = ServiceState(name, info)

    def apply_action(self, action_type: str, target: str, params: Dict[str, Any]):
        """
        Applies a remediation action to mutate the simulator state.
        """
        if action_type == "scale":
            if target in self.services:
                delta = params.get("replicas", 1)
                self.services[target].replicas += delta
                
        elif action_type == "rate_limit":
            # Add to list of active filters
            self.rate_limits.append({
                "target_service": target,
                "predicate": params.get("predicate", {}),
                "action": "drop"
            })
            
        elif action_type == "circuit_breaker":
            self.circuit_breakers[target] = params.get("enabled", True)
            
        elif action_type == "config_patch" or action_type == "rollback":
            if target in self.services:
                # Merge or replace config keys
                new_config = params.get("config", {})
                for k, v in new_config.items():
                    if isinstance(v, dict) and k in self.services[target].config:
                        self.services[target].config[k].update(v)
                    else:
                        self.services[target].config[k] = v
                
                # Add to deployment history to simulate deployment completion
                commit_id = f"patch-{uuid.uuid4().hex[:6]}"
                self.deployment_history.append({
                    "service": target,
                    "commit": commit_id,
                    "deployed_at": params.get("timestamp", "2026-07-16T20:00:00Z"),
                    "changed_files": [f"services/{target}/config.yaml"],
                    "changed_keys": list(new_config.keys())
                })
                
        elif action_type == "restart":
            if target in self.services:
                # Reset memory leak accumulation
                self.services[target].leak_accumulated_mb = 0.0
                self.services[target].queue_depth = 0

    def tick(self, minute: int, truth: Optional[Any], timestamp: str) -> Dict[str, Any]:
        """
        Executes a single time step of the simulation.
        Calculates service metrics, flows, logs, traces, and changes based on active scenario.
        """
        # 1. Determine active scenario
        scenario_id = truth.scenario_id if truth else None
        
        # 2. Inject Scenario A Config Fault Deployment at Minute 2 if not done
        if scenario_id == "retry_storm" and not self.faulty_commit_deployed:
            # Inject the bad config that causes the retry storm
            self.services["payment-service"].config = {
                "payment": {
                    "timeout_ms": 100,       # Was 5000 — now too short, provider takes 130ms
                    "max_retries": -1,       # Unlimited retries — causes amplification storm
                    "backoff_ms": 0,         # No backoff — hammers immediately
                    "circuit_breaker_enabled": False
                }
            }
            self.deployment_history.append({
                "service": "payment-service",
                "commit": "a7f31c2",
                "deployed_at": timestamp,
                "changed_files": ["services/payment-service/config.yaml"],
                "changed_keys": ["payment.timeout_ms", "payment.max_retries", "payment.backoff_ms"]
            })
            self.faulty_commit_deployed = True
        elif scenario_id != "retry_storm" and self.faulty_commit_deployed:
            # Reset fault when scenario changes (e.g. if we cycle back)
            self.faulty_commit_deployed = False

        # 3. Baseline traffic calculation
        # Let's define the base user rates (requests per minute)
        base_login_rate = 3000
        base_stream_rate = 8000
        base_merch_rate = 1500
        
        # Apply business event multipliers
        login_mult = 1.0
        stream_mult = 1.0
        merch_mult = 1.0
        
        event_active = False
        event_data = None
        validated_viewers = 0
        
        # Scenario B and C represent a merchandise drop event
        if scenario_id in ["merch_drop_clean", "credential_stuffing"] or (scenario_id == "retry_storm" and minute >= 2):
            event_active = True
            merch_mult = 12.0  # 12x merchandise traffic
            login_mult = 8.0   # 8x logins
            stream_mult = 1.5  # 1.5x streaming
            validated_viewers = int(24000 * (1 + self.rng.uniform(-0.05, 0.05)))
            
            event_data = BusinessContext(
                timestamp=timestamp,
                event_id="merch-75",
                event_type="merchandise_drop",
                status="active",
                expected_duration_minutes=5,
                affected_services=["identity-service", "merchandise-service", "payment-service"],
                expected_multipliers={
                    "identity-service": [5.0, 10.0],
                    "merchandise-service": [10.0, 18.0],
                    "payment-service": [7.0, 14.0]
                }
            )

        # 4. Generate incoming cohorts
        # We model cohorts: "legitimate_fans" and "botnet_attackers"
        regions = ["us-east", "eu-west", "ap-south"]
        
        metrics_list: List[ServiceMetricWindow] = []
        flows_list: List[FlowWindow] = []
        logs_list: List[LogMessage] = []
        traces_list: List[TraceSpan] = []
        
        # Calculate actual traffic per service
        # Let's walk the dependency graph and compute dynamics.
        
        # Determine if attack is active (Scenario C)
        attack_active = (scenario_id == "credential_stuffing")
        
        # Let's compute offered load at edge-gateway
        legit_logins = int(base_login_rate * login_mult * (1 + self.rng.uniform(-0.05, 0.05)))
        legit_streams = int(base_stream_rate * stream_mult * (1 + self.rng.uniform(-0.05, 0.05)))
        legit_merch = int(base_merch_rate * merch_mult * (1 + self.rng.uniform(-0.05, 0.05)))
        
        attack_logins = 0
        if attack_active:
            # Inject a massive credential stuffing attack
            attack_logins = int(60000 * (1 + self.rng.uniform(-0.1, 0.1)))
            
        # Apply Rate Limits (from Agent remediation)
        # Check if any rate limits block the attack logins cohort
        # Let's say the rate limit filters "unverified sessions" or specific "cohort-91"
        attack_blocked = False
        for rl in self.rate_limits:
            if rl["target_service"] == "identity-service" or rl["target_service"] == "edge-gateway":
                pred = rl["predicate"]
                if pred.get("cohort_id") == "cohort-91" or pred.get("invalid_credentials_only") is True:
                    attack_blocked = True
                    
        actual_attack_logins = 0 if attack_blocked else attack_logins
        
        # 5. Service Simulation Engine (simplified queue & amplification model)
        # We solve the offered load, latencies, and queues.
        
        # --- IDENTITY-SERVICE ---
        # Offered logins
        offered_logins = legit_logins + actual_attack_logins
        id_state = self.services["identity-service"]
        id_capacity = id_state.replicas * id_state.capacity_per_replica
        
        # Memory leak simulation
        if scenario_id == "memory_leak":
            id_state.leak_accumulated_mb += offered_logins * 0.005  # leak per request
            if id_state.leak_accumulated_mb > 4000.0:
                # extreme memory pressure, degrade capacity
                id_capacity = int(id_capacity * 0.2)
                
        id_utilization = offered_logins / max(id_capacity, 1)
        id_queue = max(0, offered_logins - id_capacity)
        id_state.queue_depth = id_queue
        
        # Latency calculation
        id_queue_delay = (id_queue / max(id_capacity, 1)) * 200.0
        id_latency = id_state.base_latency_ms + id_queue_delay + self.rng.exponential(5.0)
        
        # Success and failures
        # Legitimate login has 90% success, 10% invalid creds
        # Attack logins have 1% success, 99% invalid creds
        legit_successes = int(legit_logins * 0.9)
        legit_invalid = legit_logins - legit_successes
        
        attack_successes = int(actual_attack_logins * 0.01)
        attack_invalid = actual_attack_logins - attack_successes
        
        total_successes = legit_successes + attack_successes
        total_invalid = legit_invalid + attack_invalid
        total_server_errors = 0
        
        # If CPU/Memory is saturated, errors occur
        if id_utilization > 1.2 or id_state.leak_accumulated_mb > 3500.0:
            total_server_errors = int(offered_logins * (0.1 + min(0.8, (id_utilization - 1.2) * 0.5)))
            total_successes = max(0, total_successes - total_server_errors)
            
        id_state.cpu_percent = min(99.0, 10.0 + id_utilization * 80.0 + self.rng.uniform(-5, 5))
        id_state.memory_mb = 1000.0 + id_state.leak_accumulated_mb + id_utilization * 400.0
        
        # Traces & Logs for Identity Service
        if total_server_errors > 0:
            logs_list.append(LogMessage(
                timestamp=timestamp,
                service="identity-service",
                level="ERROR",
                message=f"Internal database timeout acquiring connection: {total_server_errors} errors/min"
            ))
            
        # Append identity-service metrics
        metrics_list.append(ServiceMetricWindow(
            timestamp=timestamp,
            service="identity-service",
            region="global",
            endpoint="/login",
            requests=offered_logins,
            validated_sessions=legit_logins, # Legit sessions
            successes=total_successes,
            invalid_credentials=total_invalid,
            server_errors=total_server_errors,
            internal_rpcs=offered_logins,
            retries=0,
            timeouts=total_server_errors,
            p50_latency_ms=min(id_latency, 5000.0),
            p95_latency_ms=min(id_latency * 1.8, 8000.0),
            cpu_percent=id_state.cpu_percent,
            memory_mb=id_state.memory_mb,
            queue_depth=id_state.queue_depth,
            replicas=id_state.replicas
        ))

        # --- STREAMING-SERVICE ---
        # Very simple streaming simulator (no major issues, acts as control)
        stream_state = self.services["streaming-service"]
        stream_cap = stream_state.replicas * stream_state.capacity_per_replica
        stream_util = legit_streams / max(stream_cap, 1)
        stream_latency = stream_state.base_latency_ms + (stream_util * 15.0)
        
        metrics_list.append(ServiceMetricWindow(
            timestamp=timestamp,
            service="streaming-service",
            region="global",
            endpoint="/stream",
            requests=legit_streams,
            validated_sessions=legit_streams,
            successes=legit_streams,
            invalid_credentials=0,
            server_errors=0,
            internal_rpcs=legit_streams,
            retries=0,
            timeouts=0,
            p50_latency_ms=stream_latency,
            p95_latency_ms=stream_latency * 1.5,
            cpu_percent=min(95.0, 5.0 + stream_util * 70.0),
            memory_mb=1200.0 + stream_util * 200.0,
            queue_depth=0,
            replicas=stream_state.replicas
        ))

        # --- PAYMENT-SERVICE & MERCHANDISE-SERVICE (Scenario A retry storm) ---
        pay_state = self.services["payment-service"]
        merch_state = self.services["merchandise-service"]
        
        # Payment service details
        pay_config = pay_state.config.get("payment", {})
        timeout_ms = pay_config.get("timeout_ms", 100)
        max_retries = pay_config.get("max_retries", -1)
        backoff_ms = pay_config.get("backoff_ms", 0)
        circuit_breaker = pay_config.get("circuit_breaker_enabled", False)
        
        # Base payment latency rises when scenario is retry_storm or merch surge (simulated backend delay)
        provider_base_latency = 80.0
        if scenario_id == "retry_storm" and minute >= 2:
            provider_base_latency = 130.0  # Causes it to exceed 100ms timeout
        elif scenario_id == "merch_drop_clean":
            provider_base_latency = 85.0   # Slight rise but safe for 1500ms timeout
            
        # Is payment provider latent?
        pay_provider_latency = provider_base_latency + self.rng.uniform(-5.0, 5.0)
        
        # Calculate how many retries occur
        # If timeout_ms is 100 and latency is 130, every attempt fails
        pay_timeout_occurred = (pay_provider_latency > timeout_ms)
        
        # Calculate offered payments at payment-service from merchandise-service
        # For each merchandise checkout, there is 1 payment.
        # But if payment service times out or fails, merchandise-service might retry or return error.
        offered_payments = legit_merch
        
        # Circuit breaker logic
        if circuit_breaker and self.circuit_breakers.get("payment-service", False):
            # If agent enabled circuit breaker, block downstream payment calls to save merchant service
            pay_timeout_occurred = False
            offered_payments = 0
            
        actual_retries = 0
        actual_timeouts = 0
        pay_successes = offered_payments
        pay_failures = 0
        
        if offered_payments > 0 and pay_timeout_occurred:
            # If max_retries is unlimited (-1), each request retries a lot in a loop.
            # We cap the simulator internal retry loop at 10 to avoid crash, but simulate high numbers
            if max_retries == -1:
                retry_factor = 8.0  # 8x retry amplification
                actual_retries = int(offered_payments * retry_factor)
                actual_timeouts = offered_payments + actual_retries
                pay_successes = 0
                pay_failures = offered_payments
                
                # Log storm
                logs_list.append(LogMessage(
                    timestamp=timestamp,
                    service="payment-service",
                    level="WARN",
                    message=f"payment timeout after {timeout_ms}ms, retry attempt amplified"
                ))
                logs_list.append(LogMessage(
                    timestamp=timestamp,
                    service="payment-service",
                    level="ERROR",
                    message="connection pool exhausted acquiring payment-provider socket"
                ))
            else:
                # Limited retries (e.g. 3 retries)
                retry_factor = min(max_retries, 3)
                actual_retries = int(offered_payments * retry_factor * 0.8)
                actual_timeouts = int(offered_payments * 0.2) # only 20% timeout if retry works
                pay_successes = offered_payments - actual_timeouts
                pay_failures = actual_timeouts
                
                logs_list.append(LogMessage(
                    timestamp=timestamp,
                    service="payment-service",
                    level="INFO",
                    message=f"payment retry attempt successful within limits"
                ))
        
        # Calculate service metrics
        pay_total_requests = offered_payments + actual_retries
        pay_capacity = pay_state.replicas * pay_state.capacity_per_replica
        pay_utilization = pay_total_requests / max(pay_capacity, 1)
        
        pay_queue = max(0, pay_total_requests - pay_capacity)
        pay_state.queue_depth = pay_queue
        
        # Latency of payment service including queue delay and backend provider latency
        pay_queue_delay = (pay_queue / max(pay_capacity, 1)) * 300.0
        pay_service_latency = pay_provider_latency + pay_queue_delay
        
        pay_state.cpu_percent = min(99.0, 15.0 + pay_utilization * 80.0)
        pay_state.memory_mb = 600.0 + (pay_queue * 2.0)
        
        metrics_list.append(ServiceMetricWindow(
            timestamp=timestamp,
            service="payment-service",
            region="global",
            endpoint="/authorize",
            requests=pay_total_requests,
            validated_sessions=offered_payments,
            successes=pay_successes,
            invalid_credentials=0,
            server_errors=pay_failures,
            internal_rpcs=pay_total_requests,
            retries=actual_retries,
            timeouts=actual_timeouts,
            p50_latency_ms=min(pay_service_latency, 6000.0),
            p95_latency_ms=min(pay_service_latency * 1.8, 10000.0),
            cpu_percent=pay_state.cpu_percent,
            memory_mb=pay_state.memory_mb,
            queue_depth=pay_state.queue_depth,
            replicas=pay_state.replicas
        ))
        
        # Merchandise Service
        # Merchandise depends on inventory and payment.
        # If payment is slow or failing, merchandise suffers.
        merch_cap = merch_state.replicas * merch_state.capacity_per_replica
        
        # If payment service is failing, merchandise checkout fails
        merch_successes = legit_merch
        merch_errors = 0
        
        if pay_failures > 0:
            merch_errors = pay_failures
            merch_successes = max(0, legit_merch - merch_errors)
            
        merch_latency = merch_state.base_latency_ms + pay_service_latency * (legit_merch / max(legit_merch, 1))
        merch_util = legit_merch / max(merch_cap, 1)
        
        merch_state.cpu_percent = min(98.0, 10.0 + merch_util * 70.0 + (10.0 if pay_failures > 0 else 0.0))
        merch_state.memory_mb = 800.0 + merch_util * 300.0
        
        metrics_list.append(ServiceMetricWindow(
            timestamp=timestamp,
            service="merchandise-service",
            region="global",
            endpoint="/checkout",
            requests=legit_merch,
            validated_sessions=legit_merch,
            successes=merch_successes,
            invalid_credentials=0,
            server_errors=merch_errors,
            internal_rpcs=legit_merch * 2,
            retries=0,
            timeouts=merch_errors,
            p50_latency_ms=min(merch_latency, 8000.0),
            p95_latency_ms=min(merch_latency * 1.5, 12000.0),
            cpu_percent=merch_state.cpu_percent,
            memory_mb=merch_state.memory_mb,
            queue_depth=0,
            replicas=merch_state.replicas
        ))
        
        # --- TRAFFIC FLOWS (For L7 DDoS / Credential stuffing) ---
        # Flow window output for identity-service login endpoints.
        # We generate flow records for cohort-91 (attackers) and cohort-legit.
        if attack_active:
            # Attacker Flow
            flows_list.append(FlowWindow(
                timestamp=timestamp,
                cohort_id="cohort-91",
                Spkts=int(actual_attack_logins * 6),
                Dpkts=int(actual_attack_logins * 4),
                Sbytes=int(actual_attack_logins * 480),
                Dbytes=int(actual_attack_logins * 320),
                Rate=float(actual_attack_logins / 10.0),
                sttl=64,
                dttl=53,
                Sload=float(actual_attack_logins * 64),
                Dload=float(actual_attack_logins * 42),
                dloss=int(actual_attack_logins * 0.005),
                Sintpkt=0.012,
                Dintpkt=0.015,
                Sjit=0.002,
                Djit=0.003,
                ct_src_dport_ltm=85,
                ct_dst_src_ltm=80
            ))
            
        # Legit Flow
        flows_list.append(FlowWindow(
            timestamp=timestamp,
            cohort_id="cohort-legit",
            Spkts=int(legit_logins * 5),
            Dpkts=int(legit_logins * 5),
            Sbytes=int(legit_logins * 400),
            Dbytes=int(legit_logins * 500),
            Rate=float(legit_logins / 60.0),
            sttl=128,
            dttl=124,
            Sload=float(legit_logins * 10),
            Dload=float(legit_logins * 12),
            dloss=0,
            Sintpkt=0.15,
            Dintpkt=0.18,
            Sjit=0.04,
            Djit=0.05,
            ct_src_dport_ltm=3,
            ct_dst_src_ltm=2
        ))

        # --- TRACES (Scenario A retry storm traces) ---
        # Generate trace samples for checkout and login
        if offered_payments > 0:
            trace_status = "timeout" if pay_timeout_occurred else "success"
            traces_list.append(TraceSpan(
                trace_id=f"tr-{uuid.uuid4().hex[:6]}",
                span_id="sp-04",
                parent_span_id="sp-03",
                source_service="merchandise-service",
                target_service="payment-service",
                operation="authorize_payment",
                duration_ms=pay_service_latency,
                status=trace_status,
                retry_attempt=actual_retries // max(offered_payments, 1)
            ))
            
        if offered_logins > 0:
            trace_status = "error" if total_server_errors > 0 else "success"
            traces_list.append(TraceSpan(
                trace_id=f"tr-{uuid.uuid4().hex[:6]}",
                span_id="sp-01",
                parent_span_id=None,
                source_service="edge-gateway",
                target_service="identity-service",
                operation="login",
                duration_ms=id_latency,
                status=trace_status,
                retry_attempt=0
            ))

        # Serialize all Pydantic objects to plain dicts so JSON serialization works cleanly
        return {
            "timestamp": timestamp,
            "validated_viewers": validated_viewers,
            "business_context": event_data.dict() if event_data else None,
            "service_metrics": [m.dict() for m in metrics_list],
            "network_flow_windows": [f.dict() for f in flows_list],
            "logs": [l.dict() for l in logs_list],
            "traces": [t.dict() for t in traces_list],
            "deployment_changes": self.get_deployment_changes(timestamp),
            "configuration_snapshots": [s.dict() for s in self.get_configuration_snapshots()]
        }

    def get_deployment_changes(self, current_time_str: str) -> List[Dict[str, Any]]:
        # Return deployments made up to current simulated time
        current_time = datetime.strptime(current_time_str, "%Y-%m-%dT%H:%M:%SZ")
        changes = []
        for dep in self.deployment_history:
            dep_time = datetime.strptime(dep["deployed_at"], "%Y-%m-%dT%H:%M:%SZ")
            if dep_time <= current_time:
                changes.append(dep)
        return changes

    def get_configuration_snapshots(self) -> List[ConfigurationSnapshot]:
        snapshots = []
        for name, svc in self.services.items():
            if svc.config:
                snapshots.append(ConfigurationSnapshot(
                    service=name,
                    config=svc.config
                ))
        return snapshots
