"""
TradeFlow AI — Agentic AI-Powered Supply Chain Intelligence
Step 6: Interactive Web Dashboard

Main Streamlit application entry point using st.navigation() + st.Page().
"""

import os
import sys
import streamlit as st

# ── Path setup ──
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(APP_DIR)

# Data directory discovery (checks env var first, then common locations)
DATA_DIR_CANDIDATES = [
    os.environ.get("TRADEFLOW_DATA_DIR"),
    os.path.join(APP_DIR, "data"),
    os.path.join(PARENT_DIR, "Datasets"),
    os.path.join(APP_DIR, "Datasets"),
]

DATA_DIR = None
for candidate in DATA_DIR_CANDIDATES:
    if candidate and os.path.exists(candidate) and os.path.exists(os.path.join(candidate, "products.csv")):
        DATA_DIR = candidate
        break

if DATA_DIR is None:
    st.error("Data directory not found. Set the TRADEFLOW_DATA_DIR environment variable "
             "to point to the folder containing products.csv and the other CSV files.")
    st.stop()

if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from components.styling import inject_css
from components.metrics import load_data


# ── Page configuration ──
st.set_page_config(
    page_title="TradeFlow AI — Supply Chain Intelligence",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════════════
# Shared state helpers
# ══════════════════════════════════════════════════════════════
def _ensure_shared_state():
    """Initialise shared session-state keys on first run."""
    if "scenario" not in st.session_state:
        st.session_state["scenario"] = "demonstration"
    if "data_dir" not in st.session_state:
        st.session_state["data_dir"] = DATA_DIR


@st.cache_data(ttl=300)
def _load_cached_data(data_dir: str) -> dict:
    return load_data(data_dir)


@st.cache_resource
def _get_orchestrator(data_dir: str):
    try:
        from tradeflow_agents import OrchestratorAgent
        db_path = os.path.join(data_dir, "tradeflow_agents.db")
        return OrchestratorAgent(data_dir, db_path=db_path)
    except Exception as e:
        st.error(f"Failed to initialize orchestrator: {e}")
        return None


def _render_sidebar():
    """Sidebar: branding + scenario selector + data-dir footer."""
    st.sidebar.markdown("# 📦 TradeFlow AI")
    st.sidebar.caption("Agentic AI-Powered Supply Chain Intelligence")
    st.sidebar.markdown("---")

    st.sidebar.markdown("### Scenario Selection")
    scenario = st.sidebar.radio(
        "Select Inventory Scenario",
        options=["demonstration", "original"],
        format_func=lambda x: "📦 Inventory Imbalance (Demo)" if x == "demonstration" else "🏭 Original Overstocking",
        key="scenario",
    )

    scenario_label = "Inventory Imbalance" if scenario == "demonstration" else "Original Overstocking"
    scenario_desc = "Shortages, excess stock, and transfer opportunities" if scenario == "demonstration" else "High inventory, ageing, minimal transfer needs"
    with st.sidebar.container(border=True):
        st.caption("Current Scenario")
        st.markdown(f"**{scenario_label}**")
        st.caption(scenario_desc)

    st.sidebar.markdown("---")

    if DATA_DIR:
        with st.sidebar.container(border=True):
            st.caption("Data Directory")
            st.code(DATA_DIR, language="text")

    st.sidebar.caption("TradeFlow AI v1.0 — Step 6 | FutureMindz Dubai Hackathon")


def _get_shared_context():
    """Return (data, scenario, orchestrator) for the current page."""
    _ensure_shared_state()
    data_dir = st.session_state.get("data_dir", DATA_DIR)
    scenario = st.session_state.get("scenario", "demonstration")
    data = _load_cached_data(data_dir) if data_dir else {}
    orchestrator = _get_orchestrator(data_dir) if data_dir else None
    return data, scenario, orchestrator


# ══════════════════════════════════════════════════════════════
# Page functions (each is a st.Page target)
# ══════════════════════════════════════════════════════════════
def page_executive_dashboard():
    inject_css()
    data, scenario, _ = _get_shared_context()
    if not data:
        st.error("Data directory not found.")
        return
    from pages import executive_dashboard
    executive_dashboard.render(data, scenario)


def page_demand_forecasting():
    inject_css()
    data, scenario, _ = _get_shared_context()
    if not data:
        st.error("Data directory not found.")
        return
    from pages import demand_forecasting
    demand_forecasting.render(data, scenario)


def page_inventory_intelligence():
    inject_css()
    data, scenario, _ = _get_shared_context()
    if not data:
        st.error("Data directory not found.")
        return
    from pages import inventory_intelligence
    inventory_intelligence.render(data, scenario)


def page_transfer_optimization():
    inject_css()
    data, scenario, orchestrator = _get_shared_context()
    if not data:
        st.error("Data directory not found.")
        return
    from pages import transfer_optimization
    transfer_optimization.render(data, scenario, orchestrator)


def page_agent_control_center():
    inject_css()
    data, scenario, orchestrator = _get_shared_context()
    if not data:
        st.error("Data directory not found.")
        return
    from pages import agent_control_center
    agent_control_center.render(data, scenario, orchestrator)


def page_approval_center():
    inject_css()
    data, scenario, orchestrator = _get_shared_context()
    if not data:
        st.error("Data directory not found.")
        return
    from pages import approval_center
    approval_center.render(data, scenario, orchestrator)


def page_demand_uncertainty():
    inject_css()
    data, scenario, _ = _get_shared_context()
    if not data:
        st.error("Data directory not found.")
        return
    from pages import demand_uncertainty
    demand_uncertainty.render(data, scenario)


# ══════════════════════════════════════════════════════════════
# Main — st.navigation() multipage wiring
# ══════════════════════════════════════════════════════════════
_ensure_shared_state()
_render_sidebar()

pages = [
    st.Page(page_executive_dashboard, title="Executive Dashboard", icon="📊"),
    st.Page(page_demand_forecasting, title="Demand Forecasting", icon="📈"),
    st.Page(page_inventory_intelligence, title="Inventory Intelligence", icon="🎯"),
    st.Page(page_transfer_optimization, title="Transfer Optimization", icon="🔄"),
    st.Page(page_agent_control_center, title="Agent Control Center", icon="🤖"),
    st.Page(page_demand_uncertainty, title="Demand Uncertainty", icon="📉"),
    st.Page(page_approval_center, title="Approval Center", icon="✅"),
]

pg = st.navigation(pages, position="sidebar")
pg.run()
