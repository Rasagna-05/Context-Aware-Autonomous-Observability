import streamlit as st
import httpx
import pandas as pd
import plotly.graph_objects as go
import time

# Configure page structure and dark theme
st.set_page_config(
    page_title="Cisco Observability Twin Dashboard",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Backend API endpoint URL
BACKEND_URL = "http://127.0.0.1:8000/telemetry"

# Inject custom CSS for premium look and feel
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #0b0f19;
        color: #f1f5f9;
    }
    
    /* Sidebar styled container */
    [data-testid="stSidebar"] {
        background-color: #0f172a !important;
        border-right: 1px solid #1e293b;
    }
    
    /* Sleek card styling */
    .glass-card {
        background-color: rgba(30, 41, 59, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        backdrop-filter: blur(8px);
    }
</style>
""", unsafe_allow_html=True)

# Fetch latest telemetry data from FastAPI
try:
    response = httpx.get(BACKEND_URL)
    telemetry = response.json()
except Exception as e:
    st.error("🔌 Backend Offline: Cannot connect to FastAPI server on http://127.0.0.1:8000")
    st.markdown("""
    **To launch the hackathon Digital Twin backend service:**
    - Run: `uvicorn backend:app --port 8000`
    """)
    st.stop()

# Initialize session state for charting history
if "history" not in st.session_state:
    st.session_state.history = []

# Construct current data point
data_point = {
    "Tick": len(st.session_state.history) + 1,
    "Time": time.strftime("%H:%M:%S"),
    "Total Requests": telemetry["total_requests"],
    "Expected Requests": telemetry["expected_requests"],
    "Unexplained Residual": telemetry["residual"],
    "r1": telemetry["r1"],
    "r2": telemetry["r2"],
    "r3": telemetry["r3"],
    "r4": telemetry["r4"],
    "r5": telemetry["r5"],
    "Latency": telemetry["p95_latency"]
}

# Append and cap history at 30 points to represent a rolling timeline
st.session_state.history.append(data_point)
if len(st.session_state.history) > 30:
    st.session_state.history.pop(0)

# Build pandas dataframe for Plotly Express
df_history = pd.DataFrame(st.session_state.history)

# ==========================================
# SIDEBAR MONITOR
# ==========================================
with st.sidebar:
    st.image("https://www.cisco.com/c/dam/assets/prod/logos/cisco-logo-blueprint.png", width=100)
    st.title("Twin State variables")
    st.markdown("---")
    
    st.markdown(f"**Logical Context:** `{telemetry['context']}`")
    st.markdown(f"**Legitimate Demand:** `{telemetry['legitimate_fans']:,} req/min`")
    st.markdown(f"**Botnet Attack Traffic:** `{telemetry['botnet_ips']:,} req/min`")
    st.markdown(f"**RPC Retry Multiplier:** `{telemetry['retry_multiplier']}x`")
    
    if telemetry["mitigation_applied"]:
        st.success("✅ Mitigations: ACTIVE")
    else:
        st.warning("⚠️ Mitigations: INACTIVE")

    # Add quick simulation reset action
    if st.button("🔄 Reset Global Variables", use_container_width=True):
        try:
            httpx.post("http://127.0.0.1:8000/mutate", json={
                "context": "NORMAL",
                "legitimate_fans": 1000,
                "botnet_ips": 0,
                "retry_multiplier": 1.0,
                "mitigation_applied": False
            })
            st.session_state.history = []
            st.rerun()
        except Exception as e:
            st.error(f"Error resetting state: {e}")

# ==========================================
# SECTION 1: TOP BAR (CONTEXT HEADER)
# ==========================================
st.markdown("<h2 style='margin-bottom:0; font-weight:700;'>📡 Cisco Cognitive Observability Platform</h2>", unsafe_allow_html=True)
st.markdown("<p style='color:#64748b; font-size:0.95rem; margin-top:2px;'>Digital Twin Control Center — Pitch Mode Sandbox</p>", unsafe_allow_html=True)

# Context banner
ctx = telemetry["context"]
mit = telemetry["mitigation_applied"]

if ctx == "NORMAL":
    banner_color = "#10b981"
    banner_text = "🟢 System Context: NORMAL OPERATIONS"
elif ctx == "MERCH_DROP":
    if telemetry["botnet_ips"] > 0:
        banner_color = "#ef4444"
        banner_text = "🔴 System Context: FLASH MERCH DROP SURGE + BOTNET THREAT IN PROGRESS"
    else:
        banner_color = "#f59e0b"
        banner_text = "🟡 System Context: ACTIVE MERCH DROP SURGE (LEGITIMATE)"
else:
    banner_color = "#ef4444"
    banner_text = f"🔴 System Context: {ctx}"

st.markdown(f"""
<div style="background-color: rgba(30,41,59,0.5); border-left: 6px solid {banner_color}; padding: 14px 20px; border-radius: 6px; margin: 15px 0;">
    <h3 style="margin:0; color:{banner_color}; font-size:1.25rem;">{banner_text}</h3>
</div>
""", unsafe_allow_html=True)

# ==========================================
# SECTION 2: SURGE DECOMPOSITION CHART
# ==========================================
st.markdown("### 📊 Live Traffic Surge Decomposition")

# Plotly traffic graph
fig = go.Figure()

# Expected Requests line
fig.add_trace(go.Scatter(
    x=df_history["Tick"],
    y=df_history["Expected Requests"],
    name="Event-Expected Requests (Baseline)",
    mode="lines",
    line=dict(color="#38bdf8", width=2.5, dash="dash")
))

# Total Requests filled area (Visualizing gap/unexplained residual)
fig.add_trace(go.Scatter(
    x=df_history["Tick"],
    y=df_history["Total Requests"],
    name="Total Requests (Observed)",
    mode="lines+markers",
    fill="tonexty",
    fillcolor="rgba(239, 68, 68, 0.18)" if telemetry["residual"] > 0 else "rgba(16, 185, 129, 0.05)",
    line=dict(
        color="#ef4444" if telemetry["botnet_ips"] > 0 or telemetry["r4"] > 5.0 else "#10b981", 
        width=3.5
    ),
    marker=dict(size=5)
))

fig.update_layout(
    template="plotly_dark",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=10, b=40),
    height=300,
    hovermode="x unified",
    xaxis=dict(
        title="Simulated Ticks (Polling Intervals)",
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)"
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

st.plotly_chart(fig, use_container_width=True)

# ==========================================
# SECTION 3: INVARIANT RATIOS PANEL
# ==========================================
st.markdown("### 🧬 Observability Invariants")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    cpu_val = telemetry["r1"]
    cpu_breach = cpu_val > 0.80
    st.metric(
        label="CPU Utilization (r1)",
        value=f"{cpu_val*100:.1f}%",
        delta="Breached" if cpu_breach else "Normal",
        delta_color="inverse" if cpu_breach else "normal"
    )

with col2:
    auth_val = telemetry["r2"]
    auth_breach = auth_val < 0.30
    st.metric(
        label="Login Success (r2)",
        value=f"{auth_val*100:.1f}%",
        delta="Breached" if auth_breach else "Normal",
        delta_color="inverse" if auth_breach else "normal"
    )

with col3:
    ent_val = telemetry["r3"]
    ent_breach = ent_val < 2.0
    st.metric(
        label="Payload Entropy (r3)",
        value=f"{ent_val:.2f}",
        delta="Anomaly" if ent_breach else "Normal",
        delta_color="inverse" if ent_breach else "normal"
    )

with col4:
    rpc_val = telemetry["r4"]
    rpc_breach = rpc_val > 5.0
    st.metric(
        label="RPC Amplification (r4)",
        value=f"{rpc_val:.2f}x",
        delta="Breached" if rpc_breach else "Normal",
        delta_color="inverse" if rpc_breach else "normal"
    )

with col5:
    err_val = telemetry["r5"]
    err_breach = err_val > 0.10
    st.metric(
        label="HTTP Error Rate (r5)",
        value=f"{err_val*100:.1f}%",
        delta="Breached" if err_breach else "Normal",
        delta_color="inverse" if err_breach else "normal"
    )

# ==========================================
# SECTION 4: AGENT AI LOGIC (COGNITIVE REMEDIATOR)
# ==========================================
st.markdown("---")
st.markdown("### ⚡ Cisco Autonomous Observability Agent Console")

r2 = telemetry["r2"]
r4 = telemetry["r4"]

if r2 < 0.30:
    col_alert, col_action = st.columns([3, 1])
    with col_alert:
        st.markdown(f"""
        <div style="background-color: rgba(239, 68, 68, 0.08); border: 1px solid #ef4444; border-radius: 8px; padding: 18px; height: 110px;">
            <h4 style="color:#ef4444; margin-top:0; margin-bottom:6px;">🚨 RCA: Credential Stuffing Detected</h4>
            <p style="color:#cbd5e1; font-size:0.88rem; margin:0; line-height:1.4;">
                External botnet (cohort-91) launching dictionary attacks masking as merch drop surge.<br/>
                <b>Anomaly Fingerprint:</b> Auth success dropped to {r2*100:.1f}% (limit &lt; 30%), Payload entropy collapsed to {telemetry['r3']:.2f}.
            </p>
        </div>
        """, unsafe_allow_html=True)
    with col_action:
        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
        if st.button("🛡️ Isolate Botnet Cohort", type="primary", use_container_width=True):
            try:
                res = httpx.post("http://127.0.0.1:8000/mutate", json={"mitigation_applied": True})
                st.success("Remediation deployed.")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

elif r4 > 5.0:
    col_alert, col_action = st.columns([3, 1])
    with col_alert:
        st.markdown(f"""
        <div style="background-color: rgba(245, 158, 11, 0.08); border: 1px solid #f59e0b; border-radius: 8px; padding: 18px; height: 110px;">
            <h4 style="color:#f59e0b; margin-top:0; margin-bottom:6px;">⚠️ RCA: Internal Retry Storm Detected</h4>
            <p style="color:#cbd5e1; font-size:0.88rem; margin:0; line-height:1.4;">
                Cascading RPC failure loops triggered. Downstream timeout exceeded.<br/>
                <b>Localized Root Cause:</b> File <code>payment-service/config.yaml</code> (Commit a7f31c2 by operator@cisco.com). RPC Multiplier is {r4:.2f}x.
            </p>
        </div>
        """, unsafe_allow_html=True)
    with col_action:
        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
        if st.button("🚀 Rollback Commit", type="primary", use_container_width=True):
            try:
                res = httpx.post("http://127.0.0.1:8000/mutate", json={"mitigation_applied": True})
                st.success("Remediation deployed.")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
else:
    if mit:
        st.markdown("""
        <div style="background-color: rgba(16, 185, 129, 0.08); border: 1px dashed #10b981; border-radius: 8px; padding: 18px; text-align: center;">
            <h4 style="color:#10b981; margin:0;">✅ REMEDIATION DEPLOYED & VERIFIED</h4>
            <p style="color:#94a3b8; font-size:0.88rem; margin-top:6px; margin-bottom:0;">
                All invariant ratios restored. Observability Digital Twin has verified recovery and closed the feedback loop.
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background-color: rgba(30, 41, 59, 0.35); border: 1px dashed rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 18px; text-align: center;">
            <h4 style="color:#94a3b8; margin:0;">🔒 Systems Healthy</h4>
            <p style="color:#64748b; font-size:0.88rem; margin-top:6px; margin-bottom:0;">
                observability-agent@digitaltwin:~$ monitoring baseline parameters. All metrics within standard operational boundaries.
            </p>
        </div>
        """, unsafe_allow_html=True)

# Polling loop refresh logic
time.sleep(1.5)
st.rerun()
