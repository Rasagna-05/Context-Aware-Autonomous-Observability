# Cisco Hackathon: Context-Aware Autonomous Observability Digital Twin

This project is a high-performance, event-driven Digital Twin simulation built for a Cisco AIOps observability hackathon. It demonstrates real-time metric collection, mathematical ratio invariant analysis, Root-Cause Analysis (RCA) classification with confidence scoring, and closed-loop human-in-the-loop (HITL) remediations.

---

## 1. System Architecture

The project has been refactored from a mock static simulation into a decoupled distributed microservices layout running on three distinct local ports:

```text
  [ Traffic Generators ] ──(Real HTTP Requests)──► [ Target Platform (Port 8001) ]
                                                          ▲
                                                          │ (Polled metrics every 1s)
                                                          ▼
  [ Streamlit UI Portal (Port 8501) ] ◄──(JSON API)─── [ Observability Agent (Port 8000) ]
```

### Components

1.  **Target Platform (`target_platform.py` - Port 8001)**:
    *   An async FastAPI dummy production microservice.
    *   Tracks transaction throughput, login requests, auth successes, and internal RPCs in memory.
    *   Generates continuous, realistic ambient background traffic (**450 to 750 requests/sec**) to keep the twin alive.
    *   Accepts mutations to its firewall and timeout configurations via `/admin/*` endpoints.
2.  **Observability Agent (`observability_agent.py` - Port 8000)**:
    *   An async FastAPI AIOps control plane.
    *   Polls the target service every 1.0s to ingest telemetry and compute ratio invariants ($r_1 - r_5$).
    *   Classifies incidents, computes dynamic confidence scores, and hosts remediation action logs.
3.  **Observability Portal (`dashboard_ui.py` - Port 8501)**:
    *   A premium, glassmorphic Streamlit SaaS control plane.
    *   Fetches agent state every 1.0s and renders real-time dials, traffic charts, RCA alerts, and mitigation approval triggers.

---

## 2. Invariant Math & RCA Diagnostics

The agent evaluates five dimensionless ratios to identify anomalies:

*   **$r_1$: CPU Load** (Threshold: $\le 85\%$) - Spikes to $88\%$ during botnet floods and $97\%$ under internal loop storms.
*   **$r_2$: Auth Success** (Threshold: $\ge 40\%$) - Collapses below $15\%$ during brute-force login stuffing.
*   **$r_3$: IP Shannon Entropy** (Threshold: $\ge 2.00$) - Measures client diversity; drops to $1.1$ during concentrated botnet attacks.
*   **$r_4$: RPC Amplification** (Threshold: $\le 3.0\text{x}$) - Tracks retry loops; matches `retry_config` directly.
*   **$r_5$: Client Error Rate** (Threshold: $\le 10\%$) - Measures 5xx responses; surges during timeout cascade storms.

### Decision Matrix & Precedence

*   **Retry Storm**: If $r_4 > 3.0$, the verdict is `ALERT_RETRY_STORM` (**Confidence: 97%-99.9%**). It forces **2,500ms** latency and takes strict priority over external botnet metrics.
*   **Credential Stuffing**: If `botnet_active == True` or ($r_2 < 40\%$ and $r_3 < 2.0$), the verdict is `ALERT_CREDENTIAL_STUFFING` (**Confidence: 90%-99.9%**), forcing **220ms** latency.
*   **Merch Surge**: If requests exceed $5000$/sec while invariants are nominal, the verdict is `SUPPRESS_EXPECTED_EVENT` (Identified as legitimate peak promotional load).
*   **Standby**: Healthy nominal baseline (**45ms** latency, **45%** CPU).

---

## 3. Traffic Generators (Simulation Scripts)

Run these scripts from the workspace root to inject faults live during the presentation:

*   **`python 1_merch_surge.py`**: Fires 15,000 stream and 1,000 login requests over 5s (legitimate surge). Expected baseline climbs to match the spike.
*   **`python 2_botnet_attack.py`**: Triggers a credential stuffing attack, firing 80,000 logins over 5s with header tags. Expected baseline remains at 1,500, highlighting unexplained residual.
*   **`python 3_retry_storm.py`**: Commits an unstable configuration setting `max_retries = 15` on port 8001, triggering thread locks and pinning latency to 2,500ms.

---

## 4. Closed-Loop Remediation

 remediations are exposed as **Approve** buttons in the dashboard's RCA card and execute feedback loops back to port 8001:

1.  **Edge Rate-Limiting**: Blocks `X-Botnet` proxy headers at the edge gateway.
2.  **Config Rollback**: POSTs a config fix reverting target retries to 1.
3.  **Reset Simulation State**: A red button on the dashboard sidebar that clears all history logs, MTTR clocks, and target variables back to the beginning.

---

## 5. Getting Started

### Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Start Services (Three separate terminal windows)
```bash
# Terminal 1: Target Platform
.venv/bin/python target_platform.py

# Terminal 2: Observability Agent
.venv/bin/python observability_agent.py

# Terminal 3: Streamlit UI
.venv/bin/streamlit run dashboard_ui.py --server.port 8501
```

Open [http://localhost:8501](http://localhost:8501) in your browser.
