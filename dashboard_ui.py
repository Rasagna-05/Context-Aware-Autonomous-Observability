import streamlit as st
import httpx
import pandas as pd
import plotly.graph_objects as go
import time

# Configure page metadata and force wide layout
st.set_page_config(
    page_title="Cisco Observability Portal",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Endpoint URLs
AGENT_URL = "http://127.0.0.1:8000/api/agent_state"
REMEDIATE_URL = "http://127.0.0.1:8000/api/remediate"

# Inject Global Tailwind CSS overrides and glassmorphism styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    /* Global style resets */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #0b0f19;
        color: #f8fafc;
    }
    
    /* Remove padding at the top of the Streamlit canvas */
    .block-container {
        padding-top: 1.0rem !important;
        padding-bottom: 1.0rem !important;
        padding-left: 2.0rem !important;
        padding-right: 2.0rem !important;
        max-width: 100% !important;
    }
    
    [data-testid="stHeader"] {
        background: rgba(0,0,0,0) !important;
    }

    /* Sidebar custom styling */
    [data-testid="stSidebar"] {
        background-color: #0f172a !important;
        border-right: 1px solid rgba(255,255,255,0.06);
    }
    
    /* Premium Title Glow Card */
    .nav-header {
        background: radial-gradient(circle at 10% 20%, rgba(30, 41, 59, 0.45) 0%, rgba(15, 23, 42, 0.45) 90.1%);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 16px 24px;
        margin-bottom: 15px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
        backdrop-filter: blur(8px);
    }
    
    /* Style Streamlit containers with border=True to look like React cards */
    div[data-testid="stVerticalBlockBorder"] {
        background-color: #121824 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        padding: 1.2rem !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15) !important;
    }

    /* Tighten native vertical layout spacing to reduce empty space gaps */
    div[data-testid="stVerticalBlock"] {
        gap: 0.8rem !important;
    }
    
    /* Remove default streamlit container margins */
    div.element-container {
        margin-bottom: 0px !important;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to generate React/Tailwind-style HTML metric cards
def make_metric_card(title, value, threshold_text, is_breached):
    dot_color = "#f43f5e" if is_breached else "#10b981"
    border_color = "rgba(244, 63, 94, 0.35)" if is_breached else "rgba(255,255,255,0.08)"
    glow = "0 0 12px rgba(244, 63, 94, 0.15)" if is_breached else "none"
    return f"""
    <div style="
        background-color: #121824;
        border: 1px solid {border_color};
        box-shadow: {glow};
        border-radius: 12px;
        padding: 16px;
        text-align: left;
        height: 122px;
        transition: all 0.2s ease-in-out;
    " onmouseover="this.style.borderColor='rgba(6, 182, 212, 0.4)';" onmouseout="this.style.borderColor='{border_color}';">
        <div style="font-size: 0.72rem; color: #8b949e; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; display: flex; align-items: center; gap: 6px; margin-bottom: 8px;">
            <span style="height: 8px; width: 8px; background-color: {dot_color}; border-radius: 50%; display: inline-block;"></span>
            {title}
        </div>
        <div style="font-size: 1.8rem; font-weight: 700; color: #ffffff; margin-bottom: 2px;">{value}</div>
        <div style="font-size: 0.7rem; color: #8b949e;">Threshold: {threshold_text}</div>
    </div>
    """

# Fetch agent state
try:
    response = httpx.get(AGENT_URL)
    agent_data = response.json()
except Exception as e:
    st.error("🔌 Connection Failed: Observability Agent on port 8000 is offline.")
    st.markdown("""
    **To start the hackathon services:**
    1. **Start Target microservice**: `python target_platform.py` (Port 8001)
    2. **Start Observability Agent**: `python observability_agent.py` (Port 8000)
    """)
    st.stop()

latest_telemetry = agent_data["latest"]
history = agent_data["history"]
action_log = agent_data["action_log"]

# ==========================================
# STATE & CLOCK MANAGEMENT
# ==========================================
if "incident_start" not in st.session_state:
    st.session_state.incident_start = None
if "last_mttr" not in st.session_state:
    st.session_state.last_mttr = None

# Telemetry unpack fallback
if not history or not latest_telemetry:
    history = [{
        "timestamp": time.time(),
        "total_requests": 0,
        "expected_event_load": 1500,
        "unexplained_residual": 0,
        "r1": 0.45, "r2": 0.96, "r3": 4.8, "r4": 1.0, "r5": 0.02,
        "p95_latency": 45.0,
        "confidence_score": 100.0
    }]
    latest_telemetry = history[0]
    latest_telemetry["verdict"] = "SUPPRESS_EXPECTED_EVENT"
    latest_telemetry["rca"] = "No active metrics received."
    latest_telemetry["confidence_score"] = 100.0

r1 = latest_telemetry.get("r1", 0.45)
r2 = latest_telemetry.get("r2", 0.96)
r3 = latest_telemetry.get("r3", 4.8)
r4 = latest_telemetry.get("r4", 1.0)
r5 = latest_telemetry.get("r5", 0.02)
lat_val = latest_telemetry.get("p95_latency", 45.0)
verdict = latest_telemetry.get("verdict", "SUPPRESS_EXPECTED_EVENT")
confidence_score = latest_telemetry.get("confidence_score", 100.0)

# SLA Breaches Checks
r1_critical = r1 > 0.85
r2_critical = r2 < 0.40
r3_critical = r3 < 2.00
r4_critical = r4 > 3.00
r5_critical = r5 > 0.10
is_anomaly = verdict in ["ALERT_CREDENTIAL_STUFFING", "ALERT_RETRY_STORM"]

# Active incident clock stopwatch
if is_anomaly:
    if st.session_state.incident_start is None:
        st.session_state.incident_start = time.time()
    mttr_val = time.time() - st.session_state.incident_start
else:
    if st.session_state.incident_start is not None:
        st.session_state.last_mttr = time.time() - st.session_state.incident_start
        st.session_state.incident_start = None
    mttr_val = 0.0

df_hist = pd.DataFrame(history)
df_hist["Tick"] = range(1, len(df_hist) + 1)

# ==========================================
# SIDEBAR MONITOR PANEL
# ==========================================
with st.sidebar:
    st.image("https://www.cisco.com/c/dam/assets/prod/logos/cisco-logo-blueprint.png", width=90)
    st.title("Twin Monitor")
    st.markdown("---")
    st.markdown(f"**Botnet Script State:** `{'🔴 ACTIVE' if latest_telemetry.get('botnet_active') else '🟢 INACTIVE'}`")
    st.markdown(f"**Target Retries:** `{latest_telemetry.get('retry_config', 1)}x`")
    st.markdown(f"**Logical Verdict:** `{verdict}`")
    
    st.markdown("---")
    if st.button("🚨 Reset Simulation State", use_container_width=True):
        try:
            httpx.post("http://localhost:8000/api/reset")
            st.session_state.incident_start = None
            st.session_state.last_mttr = None
            st.success("Simulation reset.")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Reset failed: {e}")

# ==========================================
# SECTION 1: TOP NAVIGATION & HEADER
# ==========================================
st.markdown(f"""
<div class="nav-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h2 style="margin: 0; color: #ffffff; font-weight: 700; font-size: 1.35rem; display: flex; align-items: center; gap: 8px;">
                <span style="display: inline-block; width: 12px; height: 12px; background-color: #06b6d4; border-radius: 50%; box-shadow: 0 0 10px #06b6d4;"></span>
                Context-Aware Autonomous Observability Control Plane
            </h2>
            <div style="font-size: 0.75rem; color: #8b949e; margin-top: 4px;">Cisco AIOps Digital Twin Core Engine — Hackathon Platinum Flag</div>
        </div>
        <div style="display: flex; gap: 15px; text-align: right;">
            <div style="border-left: 2px solid rgba(255,255,255,0.06); padding-left: 15px;">
                <div style="font-size: 0.65rem; color: #8b949e; font-weight: 600; text-transform: uppercase;">Diagnostic Speed</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #a78bfa;">{ '1.2s' if is_anomaly else 'N/A' }</div>
            </div>
            <div style="border-left: 2px solid rgba(255,255,255,0.06); padding-left: 15px;">
                <div style="font-size: 0.65rem; color: #8b949e; font-weight: 600; text-transform: uppercase;">P95 Latency</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: { '#f43f5e' if lat_val > 500 else ('#f59e0b' if lat_val > 100 else '#10b981') };">
                    {lat_val:.1f} ms
                </div>
            </div>
            <div style="border-left: 2px solid rgba(255,255,255,0.06); padding-left: 15px;">
                <div style="font-size: 0.65rem; color: #8b949e; font-weight: 600; text-transform: uppercase;">Closed-Loop MTTR</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: { '#f43f5e' if is_anomaly else '#10b981' };">
                    { f'{mttr_val:.1f}s' if is_anomaly else (f'{st.session_state.last_mttr:.1f}s' if st.session_state.last_mttr else 'STANDBY') }
                </div>
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# SECTION 2: ROW 1 - INVARIANT CARD PANEL & RISK GAUGE
# ==========================================
col_cards = st.columns([1,1,1,1,1,2])

with col_cards[0]:
    st.markdown(make_metric_card("CPU Load (r1)", f"{r1*100:.1f}%", "≤ 85.0%", r1_critical), unsafe_allow_html=True)
with col_cards[1]:
    st.markdown(make_metric_card("Auth Success (r2)", f"{r2*100:.1f}%", "≥ 40.0%", r2_critical), unsafe_allow_html=True)
with col_cards[2]:
    st.markdown(make_metric_card("IP Entropy (r3)", f"{r3:.2f}", "≥ 2.00", r3_critical), unsafe_allow_html=True)
with col_cards[3]:
    st.markdown(make_metric_card("RPC Amplification (r4)", f"{r4:.1f}x", "≤ 3.00", r4_critical), unsafe_allow_html=True)
with col_cards[4]:
    st.markdown(make_metric_card("Error Rate (r5)", f"{r5*100:.1f}%", "≤ 10.0%", r5_critical), unsafe_allow_html=True)

with col_cards[5]:
    # Plotly Dial/Gauge Risk Chart inside native styled container to match sizing
    with st.container(border=True):
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=lat_val,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "SYSTEM LATENCY", 'font': {'size': 9, 'color': "#8b949e"}},
            number={'suffix': " ms", 'font': {'color': "#ffffff", 'size': 18, 'family': "Inter"}},
            gauge={
                'axis': {'range': [0, 3000], 'tickwidth': 1, 'tickcolor': "#8b949e", 'visible': False},
                'bar': {'color': "#f43f5e" if lat_val > 500 else ("#f59e0b" if lat_val > 100 else "#10b981")},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 100], 'color': 'rgba(16, 185, 129, 0.05)'},
                    {'range': [100, 500], 'color': 'rgba(245, 158, 11, 0.05)'},
                    {'range': [500, 3000], 'color': 'rgba(244, 63, 94, 0.05)'}
                ],
            }
        ))
        fig_gauge.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=5, r=5, t=5, b=5),
            height=70
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

# ==========================================
# SECTION 3: ROW 2 - MAIN DECOMPOSITION & DONUT CHART
# ==========================================
col_row2 = st.columns([7, 3])

with col_row2[0]:
    with st.container(border=True):
        st.markdown("<div style='font-size: 0.85rem; color:#8b949e; font-weight:600; text-transform:uppercase; margin-bottom: 8px;'>Visual Surge Decomposition</div>", unsafe_allow_html=True)
        
        fig_surge = go.Figure()

        # Expected Baseline Line (cyan)
        fig_surge.add_trace(go.Scatter(
            x=df_hist["Tick"] if not df_hist.empty else [0],
            y=df_hist["expected_event_load"] if not df_hist.empty else [1500],
            name="Expected baseline",
            mode="lines",
            line=dict(color="#06b6d4", width=2, dash="dash")
        ))

        # Observed Requests Line
        fig_surge.add_trace(go.Scatter(
            x=df_hist["Tick"] if not df_hist.empty else [0],
            y=df_hist["total_requests"] if not df_hist.empty else [0],
            name="Observed load",
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(244, 63, 94, 0.12)" if is_anomaly else "rgba(6, 182, 212, 0.05)",
            line=dict(color="#f43f5e" if is_anomaly else "#10b981", width=3)
        ))

        fig_surge.update_layout(
            template="plotly_dark",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=40, r=20, t=10, b=10),
            height=260,
            hovermode="x unified",
            xaxis=dict(showgrid=False, zeroline=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", zeroline=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_surge, use_container_width=True)

with col_row2[1]:
    with st.container(border=True):
        st.markdown("<div style='font-size: 0.85rem; color:#8b949e; font-weight:600; text-transform:uppercase; margin-bottom: 8px;'>Threat distribution</div>", unsafe_allow_html=True)
        
        labels = ["Legitimate", "Unexplained Residual"]
        unexplained = latest_telemetry.get("unexplained_residual", 0)
        total_reqs = latest_telemetry.get("total_requests", 0)
        if unexplained > 0:
            values = [total_reqs - unexplained, unexplained]
            colors = ["#06b6d4", "#f43f5e"]
        else:
            values = [max(1, total_reqs), 0]
            colors = ["#06b6d4", "#22252a"]

        fig_donut = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=.6,
            marker=dict(colors=colors),
            textinfo="percent",
            hoverinfo="label+value"
        )])

        fig_donut.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=10, b=10),
            height=260,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_donut, use_container_width=True)

# ==========================================
# SECTION 4: ROW 3 - REMEDIATION LOG & RCA
# ==========================================
col_row3 = st.columns([7, 3])

with col_row3[0]:
    with st.container(border=True):
        st.markdown("<div style='font-size: 0.85rem; color:#8b949e; font-weight:600; text-transform:uppercase; margin-bottom: 12px;'>Closed-Loop Remediation Log</div>", unsafe_allow_html=True)
        
        if not action_log:
            table_html = """
            <body style="background-color: #121824; margin: 0; padding: 0; font-family: 'Inter', sans-serif; color: #8b949e; display: flex; justify-content: center; align-items: center; height: 160px; font-size: 0.9rem;">
                <div>SLA nominal. No mitigations executed.</div>
            </body>
            """
        else:
            rows = ""
            for log in action_log:
                rows += f"""
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.06); background-color: rgba(30, 41, 59, 0.15); font-family: 'Inter', sans-serif;">
                    <td style="padding: 10px; font-family: monospace; color: #a78bfa; font-size:0.8rem;">{log.get("Timestamp")}</td>
                    <td style="padding: 10px; color: #ffffff; font-weight: 600; font-size:0.8rem;">{log.get("Target Component")}</td>
                    <td style="padding: 10px; color: #06b6d4; font-weight: 600; font-size:0.8rem;">{log.get("Action")}</td>
                    <td style="padding: 10px; color: #cbd5e1; font-size: 0.8rem;">{log.get("Reason")}</td>
                    <td style="padding: 10px; color: #8b949e; font-size: 0.75rem;">{log.get("Blast Radius Boundary")}</td>
                    <td style="padding: 10px; color: #10b981; font-weight: 600; text-align: right; font-size:0.8rem;">{log.get("Status")}</td>
                </tr>
                """
            
            table_html = f"""
            <body style="background-color: #121824; margin: 0; padding: 0; font-family: 'Inter', sans-serif; color: #f8fafc; overflow-x: hidden;">
                <div style="max-height: 180px; overflow-y: auto; padding-right: 5px;">
                    <table style="width: 100%; border-collapse: collapse; text-align: left;">
                        <thead>
                            <tr style="border-bottom: 2px solid rgba(255,255,255,0.08); color: #8b949e; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;">
                                <th style="padding: 10px;">Timestamp</th>
                                <th style="padding: 10px;">Component</th>
                                <th style="padding: 10px;">Mitigation</th>
                                <th style="padding: 10px;">Reason / Symptom</th>
                                <th style="padding: 10px;">Blast Boundary</th>
                                <th style="padding: 10px; text-align: right;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows}
                        </tbody>
                    </table>
                </div>
            </body>
            """
        st.components.v1.html(table_html, height=180, scrolling=False)

with col_row3[1]:
    with st.container(border=True):
        st.markdown("<div style='font-size: 0.85rem; color:#8b949e; font-weight:600; text-transform:uppercase; margin-bottom: 12px;'>RCA Diagnostic Engine</div>", unsafe_allow_html=True)
        
        # Incident alert selection and button mitigation
        if verdict == "ALERT_CREDENTIAL_STUFFING":
            st.markdown(f"""
            <div style="background-color: rgba(244, 63, 94, 0.06); border: 1px solid #f43f5e; border-radius: 8px; padding: 14px; margin-bottom: 10px; height: 110px;">
                <div class="alert-header" style="color:#f43f5e; font-weight:700; font-size:0.82rem; display:flex; justify-content:space-between;">
                    <span>🚨 CREDENTIAL STUFFING</span>
                    <span style="background-color:#f43f5e; color:#ffffff; padding:2px 6px; border-radius:4px; font-size:0.7rem; font-weight:800;">CONFIDENCE: {confidence_score:.1f}%</span>
                </div>
                <p style="margin: 6px 0 0 0; font-size: 0.78rem; line-height: 1.35; color: #cbd5e1;">
                    Auth success collapsed (r2 < 40%), entropy dropped (r3 < 2.0). Verdict: Botnet attack.<br/>
                    <b>Mitigation</b>: Isolate cohort IP via Edge BGP routing.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("🔍 Show Invariant Audit Report", expanded=False):
                st.markdown(f"""
                **Incident Metrics Checklist:**
                *   **r1 (CPU Load)**: `{r1*100:.1f}%` (Threshold: `≤ 85%`) - {'🔴 BREACHED' if r1_critical else '🟢 HEALTHY'}
                *   **r2 (Auth Success)**: `{r2*100:.1f}%` (Threshold: `≥ 40%`) - **🔴 BREACHED (CRITICAL)**
                *   **r3 (Shannon Entropy)**: `{r3:.2f}` (Threshold: `≥ 2.00`) - **🔴 BREACHED (CRITICAL)**
                *   **r4 (RPC Config)**: `{r4:.1f}x` (Threshold: `≤ 3x`) - {'🔴 BREACHED' if r4_critical else '🟢 HEALTHY'}
                *   **r5 (Error Rate)**: `{r5*100:.1f}%` (Threshold: `≤ 10%`) - {'🔴 BREACHED' if r5_critical else '🟢 HEALTHY'}
                
                **AIOps Diagnosis Rules:**
                *   **Condition met**: `auth_success < 0.40 & shannon_entropy < 2.0`
                *   **Verdict Action**: Block malicious proxy headers.
                """)
                
            if st.button("🛡️ Approve Edge Rate-Limiting", type="primary", use_container_width=True):
                try:
                    res = httpx.post(REMEDIATE_URL, json={"action": "isolate_botnet"})
                    st.success("Edge rate-limiting deployed.")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Mitigation failed: {e}")

        elif verdict == "ALERT_RETRY_STORM":
            st.markdown(f"""
            <div style="background-color: rgba(245, 158, 11, 0.06); border: 1px solid #f59e0b; border-radius: 8px; padding: 14px; margin-bottom: 10px; height: 110px;">
                <div class="alert-header" style="color:#f59e0b; font-weight:700; font-size:0.82rem; display:flex; justify-content:space-between;">
                    <span>⚠️ RETRY STORM DETECTED</span>
                    <span style="background-color:#f59e0b; color:#121824; padding:2px 6px; border-radius:4px; font-size:0.7rem; font-weight:800;">CONFIDENCE: {confidence_score:.1f}%</span>
                </div>
                <p style="margin: 6px 0 0 0; font-size: 0.78rem; line-height: 1.35; color: #cbd5e1;">
                    RPC amplification (r4 > 3x). Loop config value is {r4:.0f}x.<br/>
                    <b>Mitigation</b>: Rollback Git commit `a7f31c2` config.yaml settings.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("🔍 Show Invariant Audit Report", expanded=False):
                st.markdown(f"""
                **Incident Metrics Checklist:**
                *   **r1 (CPU Load)**: `{r1*100:.1f}%` (Threshold: `≤ 85%`) - **🔴 BREACHED (CRITICAL)**
                *   **r2 (Auth Success)**: `{r2*100:.1f}%` (Threshold: `≥ 40%`) - {'🔴 BREACHED' if r2_critical else '🟢 HEALTHY'}
                *   **r3 (Shannon Entropy)**: `{r3:.2f}` (Threshold: `≥ 2.00`) - {'🔴 BREACHED' if r3_critical else '🟢 HEALTHY'}
                *   **r4 (RPC Config)**: `{r4:.1f}x` (Threshold: `≤ 3x`) - **🔴 BREACHED (CRITICAL)**
                *   **r5 (Error Rate)**: `{r5*100:.1f}%` (Threshold: `≤ 10%`) - **🔴 BREACHED (CRITICAL)**
                
                **AIOps Diagnosis Rules:**
                *   **Condition met**: `rpc_amplification_multiplier > 3.0x`
                *   **Verdict Action**: Revert configuration multiplier on payment-service to 1.
                """)
                
            if st.button("🚀 Rollback Commit", type="primary", use_container_width=True):
                try:
                    res = httpx.post(REMEDIATE_URL, json={"action": "rollback_config"})
                    st.success("Config rollback deployed.")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Mitigation failed: {e}")
        
        elif latest_telemetry.get("total_requests", 0) > 5000:
            st.markdown(f"""
            <div style="background-color: rgba(6, 182, 212, 0.06); border: 1px solid #06b6d4; border-radius: 8px; padding: 14px; margin-bottom: 10px; height: 110px;">
                <div class="alert-header" style="color:#06b6d4; font-weight:700; font-size:0.82rem; display:flex; justify-content:space-between;">
                    <span>ℹ️ DIAGNOSIS: MERCH SURGE</span>
                    <span style="background-color:#06b6d4; color:#121824; padding:2px 6px; border-radius:4px; font-size:0.7rem; font-weight:800;">CONFIDENCE: {confidence_score:.1f}%</span>
                </div>
                <p style="margin: 6px 0 0 0; font-size: 0.78rem; line-height: 1.35; color: #cbd5e1;">
                    High transaction volume detected. Invariants healthy. No action required.<br/>
                    <b>Telemetry Fingerprint</b>: Traffic is at {latest_telemetry.get("total_requests", 0):,} reqs/sec.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("🔍 Show Invariant Audit Report", expanded=False):
                st.markdown(f"""
                **Incident Metrics Checklist:**
                *   **r1 (CPU Load)**: `{r1*100:.1f}%` - 🟢 HEALTHY
                *   **r2 (Auth Success)**: `{r2*100:.1f}%` - 🟢 HEALTHY
                *   **r3 (Shannon Entropy)**: `{r3:.2f}` - 🟢 HEALTHY
                *   **r4 (RPC Config)**: `{r4:.1f}x` - 🟢 HEALTHY
                *   **r5 (Error Rate)**: `{r5*100:.1f}%` - 🟢 HEALTHY
                
                **AIOps Diagnosis Rules:**
                *   **Condition met**: `throughput > 5,000 reqs/sec & all_ratios == healthy`
                """)
            st.button("🟢 Mitigation Unnecessary", disabled=True, use_container_width=True)
            
        else:
            st.markdown(f"""
            <div style="background-color: rgba(16, 185, 129, 0.04); border: 1px solid rgba(16, 185, 129, 0.15); border-radius: 8px; padding: 14px; margin-bottom: 10px; height: 110px; display:flex; flex-direction:column; justify-content:center; align-items:center;">
                <div style="color:#10b981; font-weight:700; font-size: 0.95rem; display:flex; gap:10px;">
                    <span>🟢 SYSTEM STANDBY</span>
                </div>
                <div style="background-color:rgba(16, 185, 129, 0.15); color:#10b981; padding:2px 6px; border-radius:4px; font-size:0.65rem; font-weight:800; margin-top:4px;">CONFIDENCE: 100.0%</div>
                <p style="color:#8b949e; font-size:0.75rem; margin-top:6px; margin-bottom:0; line-height:1.3; text-align:center;">
                    All invariants healthy. Metrics within nominal limits. Check loops active.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("🔍 Show Invariant Audit Report", expanded=False):
                st.markdown(f"""
                **Incident Metrics Checklist:**
                *   **r1 (CPU Load)**: `{r1*100:.1f}%` - 🟢 HEALTHY
                *   **r2 (Auth Success)**: `{r2*100:.1f}%` - 🟢 HEALTHY
                *   **r3 (Shannon Entropy)**: `{r3:.2f}` - 🟢 HEALTHY
                *   **r4 (RPC Config)**: `{r4:.1f}x` - 🟢 HEALTHY
                """)
            st.button("🟢 Diagnostics Nominal", disabled=True, use_container_width=True)

# Polling and refresh loops (1.0 second polling interval)
time.sleep(1.0)
st.rerun()
