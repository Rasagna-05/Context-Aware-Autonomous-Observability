from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime

class BusinessContext(BaseModel):
    timestamp: str
    event_id: str
    event_type: str
    status: str
    expected_duration_minutes: int
    affected_services: List[str]
    expected_multipliers: Dict[str, List[float]]

class ServiceMetricWindow(BaseModel):
    timestamp: str
    service: str
    region: str
    endpoint: str
    requests: int
    validated_sessions: int
    successes: int
    invalid_credentials: int
    server_errors: int
    internal_rpcs: int
    retries: int
    timeouts: int
    p50_latency_ms: float
    p95_latency_ms: float
    cpu_percent: float
    memory_mb: float
    queue_depth: int
    replicas: int

class FlowWindow(BaseModel):
    timestamp: str
    cohort_id: str
    Spkts: int
    Dpkts: int
    Sbytes: int
    Dbytes: int
    Rate: float
    sttl: int
    dttl: int
    Sload: float
    Dload: float
    dloss: int
    Sintpkt: float
    Dintpkt: float
    Sjit: float
    Djit: float
    ct_src_dport_ltm: int
    ct_dst_src_ltm: int

class TraceSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    source_service: str
    target_service: str
    operation: str
    duration_ms: float
    status: str  # success, timeout, error
    retry_attempt: int

class LogMessage(BaseModel):
    timestamp: str
    service: str
    level: str  # INFO, WARN, ERROR
    message: str
    request_id: Optional[str] = None

class DeploymentMetadata(BaseModel):
    service: str
    commit: str
    deployed_at: str
    changed_files: List[str]
    changed_keys: List[str]

class ConfigurationSnapshot(BaseModel):
    service: str
    config: Dict[str, Any]

class PublicObservation(BaseModel):
    timestamp: str
    business_context: Optional[BusinessContext] = None
    service_metrics: List[ServiceMetricWindow] = Field(default_factory=list)
    network_flow_windows: List[FlowWindow] = Field(default_factory=list)
    logs: List[LogMessage] = Field(default_factory=list)
    traces: List[TraceSpan] = Field(default_factory=list)
    deployment_changes: List[DeploymentMetadata] = Field(default_factory=list)
    configuration_snapshots: List[ConfigurationSnapshot] = Field(default_factory=list)

class ActionProposal(BaseModel):
    action_id: str
    action_type: str  # rate_limit, scale, circuit_breaker, config_patch, restart, rollback
    target_service: str
    risk_level: str  # low, medium, high
    confidence: float
    parameters: Dict[str, Any]
    reason: str
    rationale: Optional[str] = None        # Plain-language explanation shown on dashboard
    description: Optional[str] = None      # One-line action description
    blast_radius: Optional[str] = None     # e.g. "Minimal — single service config"
    status: str = "proposed"  # proposed, approved, rejected, executed, failed
    created_at: str

class DecisionCommit(BaseModel):
    decision_id: str
    timestamp: str
    incident_active: bool
    verdict: str  # expected_event, external_attack, operational_fault, code_config_fault, attack_and_fault, unknown
    confidence: float
    hypotheses_scores: Dict[str, float]
    evidence_chain: List[str]
    primary_root_cause: Optional[str] = None  # e.g., payment-service config error
    faulty_service: Optional[str] = None
    faulty_artifact: Optional[str] = None
    faulty_keys: List[str] = Field(default_factory=list)
    likely_commit: Optional[str] = None
    proposed_actions: List[ActionProposal] = Field(default_factory=list)
