import streamlit as st
import httpx
import pandas as pd
import plotly.graph_objects as go
import time
import textwrap


# Page config for sleek dark-themed layout
st.set_page_config(
    page_title="Cisco Cognitive Observability Digital Twin",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API endpoint URL
API_URL = "http://127.0.0.1:8000"

# Inject custom CSS for premium dark-mode, glassmorphism, and styling
st.markdown("""
<style>
    /* Global Background & Font overrides */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #0b0f17;
        color: #e2e8f0;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #0f172a !important;
        border-right: 1px solid #1e293b;
    }

    /* Custom Glassmorphic Cards */
    .card {
        background-color: rgba(30, 41, 59, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 18px;
        margin: 10px 0;
        backdrop-filter: blur(10px);
    }
    
    /* Glowing indicator badges */
    .badge {
        display: inline-block;
        padding: 6px 12px;
        font-size: 0.85rem;
        font-weight: 600;
        border-radius: 20px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .badge-healthy {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        box-shadow: 0 0 12px rgba(16, 185, 129, 0.2);
    }
    
    .badge-degraded {
        background-color: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.3);
        box-shadow: 0 0 12px rgba(245, 158, 11, 0.2);
    }
    
    .badge-critical {
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
        box-shadow: 0 0 12px rgba(239, 68, 68, 0.2);
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
        100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }
    
    /* Terminal Console */
    .console-header {
        background-color: #1e293b;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        padding: 8px 12px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        color: #94a3b8;
        border-bottom: 1px solid #334155;
        display: flex;
        align-items: center;
    }
    
    .console-dot {
        height: 10px;
        width: 10px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
    }
</style>
""", unsafe_allow_html=True)


# Helper function to generate custom HTML metric cards
def render_metric_card(title, value, threshold_text, status):
    if status == "breached":
        color = "#ef4444"
        bg_color = "rgba(239, 68, 68, 0.08)"
        border_color = "rgba(239, 68, 68, 0.25)"
        badge = "🔴 BREACHED"
    else:
        color = "#10b981"
        bg_color = "rgba(16, 185, 129, 0.06)"
        border_color = "rgba(16, 185, 129, 0.2)"
        badge = "🟢 NORMAL"
        
    return f"""
    <div style="background-color: {bg_color}; border: 1px solid {border_color}; padding: 16px; border-radius: 10px; text-align: center;">
        <div style="font-size: 0.75rem; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">{title}</div>
        <div style="font-size: 1.6rem; font-weight: 700; color: {color}; margin: 4px 0;">{value}</div>
        <div style="font-size: 0.7rem; color: #64748b; font-weight: 500;">Limit: {threshold_text}</div>
        <div style="font-size: 0.65rem; color: {color}; font-weight: bold; margin-top: 6px; letter-spacing: 0.05em;">{badge}</div>
    </div>
    """

def render_rca_report_html(report, status_badge):
    anomalies_html = "".join([f"<li style='margin-bottom:4px;'>{a}</li>" for a in report['anomalies_detected']])
    
    html = f"""
    <div style="background-color: rgba(30, 41, 59, 0.45); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 20px; margin: 10px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 10px; margin-bottom: 15px;">
            <span style="font-size: 1.15rem; font-weight: bold; color: #fb7185;">🔍 {report['incident_title']}</span>
            <div style="display: flex; gap: 8px;">
                <span style="font-size: 0.8rem; background-color: rgba(30, 41, 59, 0.8); color: #94a3b8; border: 1px solid #475569; padding: 2px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace;">{report['incident_id']}</span>
                {status_badge}
            </div>
        </div>
        
        <table style="width:100%; border-collapse:collapse; margin-bottom:15px; font-size:0.9rem;">
            <tr style="border-bottom:1px solid rgba(255,255,255,0.05); text-align: left;">
                <td style="padding:8px 0; color:#94a3b8; font-weight:600; width:30%;">Impacted Component(s):</td>
                <td style="padding:8px 0; color:#38bdf8; font-family: 'JetBrains Mono', monospace;">{', '.join(report['components_affected'])}</td>
            </tr>
            <tr style="border-bottom:1px solid rgba(255,255,255,0.05); text-align: left;">
                <td style="padding:8px 0; color:#94a3b8; font-weight:600;">Detection Metric:</td>
                <td style="padding:8px 0; color:#a78bfa; font-family: 'JetBrains Mono', monospace;">{report['trigger_conditions']}</td>
            </tr>
            <tr style="border-bottom:1px solid rgba(255,255,255,0.05); text-align: left;">
                <td style="padding:8px 0; color:#94a3b8; font-weight:600;">Source / Localization:</td>
                <td style="padding:8px 0; color:#f8fafc; font-family: 'JetBrains Mono', monospace;">{report['commit_or_origin']}</td>
            </tr>
        </table>
        
        <div style="margin-bottom:15px;">
            <span style="font-size:0.8rem; color:#94a3b8; font-weight:bold; text-transform:uppercase; letter-spacing:0.05em;">Incident Root Cause Description</span>
            <p style="font-size:0.9rem; color:#cbd5e1; margin:4px 0 0 0; line-height:1.4;">{report['root_cause']}</p>
        </div>
        
        <div style="margin-bottom:15px;">
            <span style="font-size:0.8rem; color:#94a3b8; font-weight:bold; text-transform:uppercase; letter-spacing:0.05em;">Anomalous Evidence & Metrics</span>
            <ul style="font-size:0.88rem; color:#fb7185; margin:4px 0 0 0; padding-left:20px; line-height:1.4;">
                {anomalies_html}
            </ul>
        </div>
        
        <div>
            <span style="font-size:0.8rem; color:#94a3b8; font-weight:bold; text-transform:uppercase; letter-spacing:0.05em;">Recommended Remediation Plan</span>
            <p style="font-size:0.9rem; color:#34d399; margin:4px 0 0 0; line-height:1.4;">{report['mitigation_plan']}</p>
        </div>
    </div>
    """
    return textwrap.dedent(html)


# Fetch state from FastAPI
try:
    response = httpx.get(f"{API_URL}/api/state")
    state_data = response.json()
except Exception as e:
    st.error(f"🔌 Connection Refused: Cannot connect to FastAPI Digital Twin Backend at {API_URL}")
    st.markdown("""
    **To launch the simulation services, run the following commands in separate terminals:**
    1. **Start Backend**: `uvicorn simulator:app --port 8000`
    2. **Start Frontend**: `streamlit run app.py`
    """)
    st.stop()

current_tick = state_data["current_tick"]
history = state_data["history"]
active_mitigations = state_data["active_mitigations"]
current_telemetry = history[-1]

# ==========================================
# SIDEBAR CONTROLS
# ==========================================
with st.sidebar:
    st.image("https://www.cisco.com/c/dam/assets/prod/logos/cisco-logo-blueprint.png", width=120)
    st.title("Digital Twin Control Panel")
    st.markdown("---")
    
    st.subheader("⏱️ Speed and Automations")
    play_speed = st.slider("Step Delay (seconds)", min_value=0.5, max_value=4.0, value=1.5, step=0.5)
    autoplay = st.toggle("Enable Live Auto-Play", value=False)
    
    st.subheader("🛠️ Manual Actions")
    col_step, col_reset = st.columns(2)
    with col_step:
        if st.button("➡️ Step Minute", use_container_width=True, disabled=current_tick >= 30):
            try:
                res = httpx.post(f"{API_URL}/api/step")
                st.rerun()
            except Exception as e:
                st.error(f"Error stepping: {e}")
                
    with col_reset:
        if st.button("🔄 Reset Twin", use_container_width=True):
            try:
                res = httpx.post(f"{API_URL}/api/reset")
                st.rerun()
            except Exception as e:
                st.error(f"Error resetting: {e}")
                
    st.markdown("---")
    st.markdown("""
    ### 📖 Hackathon Guidelines
    - **Ticks 1-5**: NORMAL Operations
    - **Ticks 6-12**: Legitimate MERCH DROP SURGE
    - **Ticks 13-18**: Botnet CREDENTIAL STUFFING attack masked in surge
    - **Ticks 19-24**: Post-attack RECOVERY phase
    - **Ticks 25-30**: Config fault RETRY STORM loops
    """)

# ==========================================
# SECTION 1: TOP BAR (SYSTEM SUMMARY)
# ==========================================
st.markdown("<h2 style='margin-bottom:0; font-weight:700;'>📡 Cisco Observability Hackathon | Digital Twin Control Plane</h2>", unsafe_allow_html=True)
st.markdown("<p style='color:#64748b; font-size:1rem; margin-top:2px;'>Phase 2 Sandbox — Deterministic Mock Machine Learning and Causal Remediation Loop</p>", unsafe_allow_html=True)

# Select badge color based on health status
health_val = current_telemetry["health"]
if health_val == "HEALTHY":
    badge_html = f'<span class="badge badge-healthy">🟢 HEALTHY</span>'
elif health_val == "DEGRADED":
    badge_html = f'<span class="badge badge-degraded">🟡 DEGRADED</span>'
else:
    badge_html = f'<span class="badge badge-critical">🔴 CRITICAL</span>'

# Header metrics display
col_time, col_ctx, col_status = st.columns(3)
with col_time:
    st.markdown(f"""
    <div class="card" style="text-align:center;">
        <div style="font-size:0.85rem; color:#94a3b8; font-weight:500;">Simulated Duration</div>
        <div style="font-size:1.8rem; font-weight:700; color:#38bdf8; margin: 5px 0;">Minute {current_tick} <span style="font-size:1.1rem; color:#64748b;">/ 30</span></div>
        <div style="font-size:0.75rem; color:#64748b;">1 Tick = 1 Simulated Minute</div>
    </div>
    """, unsafe_allow_html=True)

with col_ctx:
    st.markdown(f"""
    <div class="card" style="text-align:center;">
        <div style="font-size:0.85rem; color:#94a3b8; font-weight:500;">Active Business Context</div>
        <div style="font-size:1.8rem; font-weight:700; color:#fbbf24; margin: 5px 0;">{current_telemetry['context']}</div>
        <div style="font-size:0.75rem; color:#64748b;">Injected Ground Truth</div>
    </div>
    """, unsafe_allow_html=True)

with col_status:
    st.markdown(f"""
    <div class="card" style="text-align:center;">
        <div style="font-size:0.85rem; color:#94a3b8; font-weight:500;">System Health State</div>
        <div style="margin: 15px 0 10px 0;">{badge_html}</div>
        <div style="font-size:0.75rem; color:#64748b;">Determined by Heuristic Inference Engine</div>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# SECTION 2: SURGE DECOMPOSITION CHART
# ==========================================
st.markdown("### 📊 Visual Telemetry & Traffic Decomposition")

# Prepare historical dataframe
df_history = pd.DataFrame(history)

# Chart 1: Total vs Expected requests
fig_traffic = go.Figure()

# Expected baseline
fig_traffic.add_trace(go.Scatter(
    x=df_history["tick"],
    y=df_history["expected_requests"],
    name="Event-Expected requests (Baseline)",
    mode="lines+markers",
    line=dict(color="#38bdf8", width=3, dash="dash"),
    marker=dict(size=6)
))

# Total requests
fig_traffic.add_trace(go.Scatter(
    x=df_history["tick"],
    y=df_history["total_requests"],
    name="Total Requests (Observed)",
    mode="lines+markers",
    line=dict(
        color="#10b981" if health_val == "HEALTHY" else ("#f59e0b" if health_val == "DEGRADED" else "#ef4444"),
        width=4
    ),
    marker=dict(size=7)
))

# Unexplained residual shaded area
fig_traffic.add_trace(go.Scatter(
    x=df_history["tick"],
    y=df_history["residual"],
    name="Unexplained Residual (Anomaly)",
    fill="tozeroy",
    mode="lines",
    line=dict(color="rgba(239, 68, 68, 0)", width=0),
    fillcolor="rgba(239, 68, 68, 0.15)"
))

fig_traffic.update_layout(
    template="plotly_dark",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=10, b=40),
    height=320,
    hovermode="x unified",
    xaxis=dict(
        title="Simulated Minute (Tick)",
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)",
        range=[1, 30],
        dtick=2
    ),
    yaxis=dict(
        title="Requests / minute",
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)"
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1
    )
)

# Chart 2: Invariant Ratios
fig_ratios = go.Figure()
fig_ratios.add_trace(go.Scatter(
    x=df_history["tick"],
    y=df_history["r2_login_success"],
    name="Login Success (r2)",
    line=dict(color="#60a5fa", width=2.5)
))
fig_ratios.add_trace(go.Scatter(
    x=df_history["tick"],
    y=df_history["r3_entropy"],
    name="Payload Entropy (r3)",
    line=dict(color="#c084fc", width=2.5)
))
fig_ratios.add_trace(go.Scatter(
    x=df_history["tick"],
    y=df_history["r4_rpc_amplification"],
    name="RPC Amplification (r4)",
    line=dict(color="#f472b6", width=2.5)
))

fig_ratios.update_layout(
    template="plotly_dark",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=10, b=40),
    height=320,
    hovermode="x unified",
    xaxis=dict(
        title="Simulated Minute (Tick)",
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)",
        range=[1, 30],
        dtick=2
    ),
    yaxis=dict(
        title="Value / Multiplier",
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)"
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1
    )
)

# Chart 3: Latency
fig_latency = go.Figure()
fig_latency.add_trace(go.Scatter(
    x=df_history["tick"],
    y=df_history["p95_latency"],
    name="p95 Downstream Latency",
    line=dict(color="#fb7185", width=3),
    fill="tozeroy",
    fillcolor="rgba(251, 113, 133, 0.08)"
))

fig_latency.update_layout(
    template="plotly_dark",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=10, b=40),
    height=320,
    hovermode="x unified",
    xaxis=dict(
        title="Simulated Minute (Tick)",
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)",
        range=[1, 30],
        dtick=2
    ),
    yaxis=dict(
        title="Latency (ms)",
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)"
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1
    )
)

# Render charts in Tabs
tab_traffic, tab_ratios, tab_latency = st.tabs([
    "📈 Traffic Decomposition & Residuals", 
    "📊 System Invariant Ratios (r1-r5)", 
    "⏱️ Downstream p95 Latency"
])

with tab_traffic:
    st.plotly_chart(fig_traffic, use_container_width=True)
with tab_ratios:
    st.plotly_chart(fig_ratios, use_container_width=True)
with tab_latency:
    st.plotly_chart(fig_latency, use_container_width=True)

# ==========================================
# SECTION 3: INVARIANT RATIOS PANEL
# ==========================================
st.markdown("### 🧬 Telemetry Invariant Invariants (Real-Time)")

r1 = current_telemetry["r1_cpu_utilization"]
r2 = current_telemetry["r2_login_success"]
r3 = current_telemetry["r3_entropy"]
r4 = current_telemetry["r4_rpc_amplification"]
r5 = current_telemetry["r5_error_rate"]
lat = current_telemetry["p95_latency"]

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    cpu_breach = "breached" if r1 > 0.80 else "normal"
    st.markdown(render_metric_card("CPU Load (r1)", f"{r1*100:.1f}%", "≤ 80.0%", cpu_breach), unsafe_allow_html=True)
    
with col2:
    login_breach = "breached" if r2 < 0.30 else "normal"
    st.markdown(render_metric_card("Login Success (r2)", f"{r2*100:.1f}%", "≥ 30.0%", login_breach), unsafe_allow_html=True)
    
with col3:
    entropy_breach = "breached" if r3 < 2.0 else "normal"
    st.markdown(render_metric_card("Payload Entropy (r3)", f"{r3:.2f}", "≥ 2.00", entropy_breach), unsafe_allow_html=True)
    
with col4:
    rpc_breach = "breached" if r4 > 5.0 else "normal"
    st.markdown(render_metric_card("RPC Amplification (r4)", f"{r4:.2f}x", "≤ 5.00", rpc_breach), unsafe_allow_html=True)
    
with col5:
    error_breach = "breached" if r5 > 0.10 else "normal"
    st.markdown(render_metric_card("Error Rate (r5)", f"{r5*100:.1f}%", "≤ 10.0%", error_breach), unsafe_allow_html=True)
    
with col6:
    lat_breach = "breached" if lat > 500.0 else "normal"
    st.markdown(render_metric_card("p95 Latency", f"{lat:.0f} ms", "≤ 500 ms", lat_breach), unsafe_allow_html=True)

# ==========================================
# SECTION 4: ROOT CAUSE ANALYSIS (RCA) REPORTS
# ==========================================
st.markdown("---")
st.markdown("### 🔍 Root Cause Analysis (RCA) Incident Reports")

# Build list of unique incidents from history
unique_incidents = {}
for item in history:
    inf = item.get("inference", {})
    report = inf.get("rca_report")
    if report:
        inc_id = report["incident_id"]
        if inc_id not in unique_incidents:
            unique_incidents[inc_id] = {
                "report": report,
                "first_detected_tick": item["tick"],
                "mitigated": False
            }
        
        # Check if the incident's recommended action has been mitigated
        rec_action = inf.get("recommended_action")
        if rec_action and rec_action in active_mitigations:
            unique_incidents[inc_id]["mitigated"] = True

if not unique_incidents:
    st.info("ℹ️ No incident logs detected in telemetry. All system metrics operate within expectation.")
else:
    # Present incident reports in tabs
    inc_tabs = st.tabs([f"📄 {val['report']['incident_title']} ({key})" for key, val in unique_incidents.items()])
    for tab, (inc_id, inc_info) in zip(inc_tabs, unique_incidents.items()):
        with tab:
            is_mit = inc_info["mitigated"]
            if is_mit:
                status_badge = '<span style="font-size: 0.75rem; background-color: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 8px; border-radius: 4px; font-weight: bold; letter-spacing: 0.05em;">✅ MITIGATED</span>'
            else:
                status_badge = '<span style="font-size: 0.75rem; background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); padding: 2px 8px; border-radius: 4px; font-weight: bold; letter-spacing: 0.05em; animation: pulse 2s infinite;">🚨 ACTIVE ANOMALY</span>'
            
            st.html(render_rca_report_html(inc_info["report"], status_badge))

# ==========================================
# SECTION 5: AGENT CONSOLE & REMEDIATION
# ==========================================
st.markdown("---")
col_console, col_remedy = st.columns([3, 2])

with col_console:
    st.markdown("### 🖥️ Cisco Observability Agent Console")
    
    # Generate terminal logs
    logs = []
    for item in history:
        t = item["tick"]
        scen = item["scenario"]
        health = item["health"]
        inf = item["inference"]
        verdict = inf["verdict"]
        rca = inf["rca"]
        prob = inf["probability"]
        
        timestamp = f"15:{t:02d}:00"
        
        if verdict == "ALERT_CREDENTIAL_STUFFING":
            log_line = f"<span style='color:#ef4444;'>[{timestamp}] [CRITICAL] 🔴 {verdict} - Confidence: {int(prob*100)}%</span><br/>"
            log_line += f"  <span style='color:#94a3b8;'>↳ RCA: {rca}</span><br/>"
            log_line += f"  <span style='color:#60a5fa;'>↳ Action proposed: Throttle botnet cohort immediately.</span><br/>"
        elif verdict == "ALERT_INTERNAL_FAULT":
            log_line = f"<span style='color:#ef4444;'>[{timestamp}] [CRITICAL] 🔴 {verdict} - Confidence: {int(prob*100)}%</span><br/>"
            log_line += f"  <span style='color:#94a3b8;'>↳ RCA: {rca}</span><br/>"
            log_line += f"  <span style='color:#60a5fa;'>↳ Action proposed: Rollback configurations to commit a7f31c2 baseline.</span><br/>"
        else:
            log_line = f"<span style='color:#10b981;'>[{timestamp}] [INFO] 🟢 {verdict}</span> - <span style='color:#94a3b8;'>{rca}</span><br/>"
            
        logs.append(log_line)
        
    terminal_html = f"""
    <div>
        <div class="console-header">
            <span class="console-dot" style="background-color:#ef4444;"></span>
            <span class="console-dot" style="background-color:#f59e0b;"></span>
            <span class="console-dot" style="background-color:#10b981;"></span>
            <span style="margin-left: 10px;">cisco-observability-agent@digitaltwin:~$ tail -f inference.log</span>
        </div>
        <div style="background-color: #090d16; border: 1px solid #1e293b; border-top: none; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; padding: 15px; height: 230px; overflow-y: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; line-height: 1.5; color: #cbd5e1;">
            {"".join(reversed(logs))}
        </div>
    </div>
    """
    st.markdown(terminal_html, unsafe_allow_html=True)

with col_remedy:
    st.markdown("### ⚡ Causal Control & Remediation")
    
    inf = current_telemetry["inference"]
    verdict = inf["verdict"]
    recommended_action = inf["recommended_action"]
    action_display = inf["action_display"]
    
    if recommended_action:
        # Action is recommended and not already mitigated
        is_already_mitigated = recommended_action in active_mitigations
        
        if is_already_mitigated:
            st.markdown(f"""
            <div style="background-color: rgba(16, 185, 129, 0.08); border: 2px dashed #10b981; border-radius: 8px; padding: 20px; text-align: center; height: 230px; display: flex; flex-direction: column; justify-content: center; align-items: center;">
                <h4 style="color:#10b981; margin:0;">✅ REMEDIATION DEPLOYED</h4>
                <p style="color:#94a3b8; font-size:0.9rem; margin-top:8px; margin-bottom:0;">
                    Action <b>'{action_display}'</b> is currently active in the control plane.
                    System recovery is verified (MTTR metrics healthy).
                </p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background-color: rgba(239, 68, 68, 0.08); border: 2px solid #ef4444; border-radius: 8px; padding: 15px; height: 145px; margin-bottom: 12px;">
                <h4 style="color:#ef4444; margin-top:0; margin-bottom:6px;">⚠️ Remediator Action Required</h4>
                <p style="color:#e2e8f0; font-size:0.88rem; margin:0; line-height:1.4;">
                    Inference triggers <b>{verdict}</b>.<br/>
                    <b>Proposed Action</b>: {action_display}<br/>
                    <b>Impact</b>: Restores metric invariants instantly on the next tick.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🚀 Approve & Execute: {action_display}", type="primary", use_container_width=True):
                try:
                    res = httpx.post(f"{API_URL}/api/remediate", json={"action": recommended_action})
                    if res.status_code == 200:
                        st.success(f"Deployed mitigation: {action_display}!")
                        time.sleep(0.6)
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to post remediation: {e}")
    else:
        # No alert triggers currently
        # Check if we have active mitigations and show status
        if active_mitigations:
            mit_list_html = "".join([f"<li><b>{m.replace('_', ' ').title()}</b></li>" for m in active_mitigations])
            st.markdown(f"""
            <div style="background-color: rgba(30, 41, 59, 0.45); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 20px; height: 230px; display: flex; flex-direction: column; justify-content: center;">
                <h5 style="color:#10b981; margin-top:0;">🛡️ Active Control Protections</h5>
                <ul style="color:#cbd5e1; font-size:0.9rem; padding-left:20px; margin-bottom:0;">
                    {mit_list_html}
                </ul>
                <p style="color:#64748b; font-size:0.75rem; margin-top:10px; margin-bottom:0;">
                    Telemetry is forced to NORMAL. No new threat vectors detected.
                </p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background-color: rgba(30, 41, 59, 0.45); border: 1px dashed rgba(255,255,255,0.08); border-radius: 8px; padding: 20px; text-align: center; height: 230px; display: flex; flex-direction: column; justify-content: center; align-items: center;">
                <h4 style="color:#94a3b8; margin:0;">🔒 Systems Guarded</h4>
                <p style="color:#64748b; font-size:0.9rem; margin-top:8px; margin-bottom:0;">
                    No anomalies triggered. Control plane operating under suppression rules.
                </p>
            </div>
            """, unsafe_allow_html=True)

# ==========================================
# AUTO-PLAY RE-RUN LOGIC
# ==========================================
if autoplay:
    if current_tick < 30:
        time.sleep(play_speed)
        try:
            httpx.post(f"{API_URL}/api/step")
            st.rerun()
        except Exception as e:
            st.error(f"Error stepping simulation: {e}")
    else:
        st.info("Simulation reached maximum Logical Minute 30. Auto-play deactivated.")
        st.session_state["autoplay"] = False
