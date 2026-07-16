# Context-Aware Autonomous Observability Digital Twin Simulator & Agent

An end-to-end prototype implementing a continuously operating observability agent that distinguishes legitimate event traffic, external attacks, and internal faults, localizes root causes, proposes remediation actions subject to human approval, and verifies recovery.

---

## 1. Directory Structure

```text
context-aware-observability/
├── README.md
├── requirements.txt
├── config/
│   ├── services.yaml       # Microservices dependency topology configuration
│   └── policy.yaml         # Remediation action risk/approval policy mapping
├── shared/
│   └── schemas.py          # Strict Pydantic models for logs, metrics, traces, and flows
├── simulator/
│   ├── clock.py            # Thread-safe, deterministic accelerated simulation clock
│   ├── dynamics/
│   │   └── services.py     # Propagation, queuing delays, retry loops, and CPU/Mem modeling
│   ├── private/
│   │   └── ground_truth.py # Private scenario scheduler (hidden from agent)
│   └── app.py              # FastAPI server serving simulator telemetry and WebSocket stream
├── agent/
│   ├── app.py              # FastAPI agent running background inference loop
│   ├── baseline/
│   │   └── residuals.py    # Decomposes surges into explained and residual components
│   ├── features/
│   │   └── ratios.py       # Computes diagnostic indicators (retries, invalid logins, etc.)
│   ├── detection/
│   │   └── fusion.py       # Fuses ML/rules to classify attacks and faults
│   ├── rca/
│   │   └── scorer.py       # Dynamic candidate scoring and config/code localization
│   └── policy/
│   │   └── selector.py     # Maps verdicts to response ladders
├── evaluator/
│   └── app.py              # Evaluates committed agent decisions against hidden truths
├── dashboard/
│   └── static/             # Real-time dashboard served directly by the simulator (port 8000)
│       ├── index.html
│       ├── style.css       # Sleek dark-mode glassmorphic aesthetics
│       └── app.js          # SVG graph rendering, double-axis Chart.js, and API controls
├── scripts/
│   └── start_demo.sh       # Executable script to start all services and log output
└── tests/
    ├── test_leakage.py     # Verifies data-leakage boundaries (forbidden terms test)
    └── test_scenarios.py   # Verifies simulation dynamics and remediation feedback loops
```

---

## 2. Scenarios Modeled

### Scenario A: Code/Configuration Retry Storm
* **Injected Cause:** An operator deploys a commit `a7f31c2` at logical minute 2, changing `payment-service` configuration to a short `100ms` timeout, unlimited retries (`max_retries: -1`), and zero backoff.
* **Symptom Cascade:** A moderate merchandise load increases downstream payment latency beyond 100ms. Unlimited immediate retries amplify payment traffic 8x, exhausting connection pools. upstream checkouts timeout and fail, propagating to edge-gateway.
* **Agent Remediation:** The agent localizes the fault to `services/payment-service/config.yaml`, keys `payment.timeout_ms`/`max_retries`, and commit `a7f31c2`. It proposes a config patch increasing timeout to `1500ms` and capping retries at `3` with backoff.

### Scenario B: Legitimate Merchandise Surge
* **Context:** A scheduled merchandise drop event occurs.
* **Symptom Cascade:** A 12x surge in checkout requests. Ratios (success rates, invalid credential rates) remain inside expected event boundaries. Retries remain low because Scenario A was patched.
* **Agent Action:** Agent detects traffic is within the event-explained limits, suppresses alerts, and proposes simple scaling.

### Scenario C: Credential Stuffing & DDoS Attack Overlay
* **Context:** While the merchandise drop is active, an external botnet launches a credential stuffing attack on `/login`.
* **Symptom Cascade:** Login attempts surge to 90,000/min. Invalid credentials exceed 70%. Network flow logs identify a malicious cohort `cohort-91` with static TTL signatures.
* **Agent Remediation:** Agent separates the event-explained login baseline from the unexplained residual. It isolates `cohort-91` and proposes a rate limit at the edge gateway while preserving legitimate user sessions.

---

## 3. Getting Started

### 1. Requirements Installation
Ensure Python 3.12+ and virtual environment tools are installed. Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the Demo
Run the startup script:
```bash
./scripts/start_demo.sh
```
This script terminates any processes using ports 8000, 8001, and 8002, starts the Simulator, Agent, and Evaluator, and tails their logs.

### 3. Open the Dashboard
Navigate to:
* **Dashboard Portal:** [http://localhost:8000](http://localhost:8000)

### 4. Running the Tests
To run the automated leakage isolation and scenario logic checks:
```bash
.venv/bin/python3 -m unittest discover -s tests
```

---

## 4. Causal Loop Feedback & State Containment

1. **State Containment:** Ground truth scenario logs exist only in `simulator/private/ground_truth.py` and are served on `/admin/*` endpoints. The agent has access only to neutral public observations. Leakage checks are run continuously by the evaluator on port 8002.
2. **Causal Feedback:** Actions proposed by the agent are sent to the policy engine. Once approved on the dashboard, they mutate the actual system parameters in the simulator. The simulator recalculates offered load, queue depths, latencies, and errors for subsequent ticks.
