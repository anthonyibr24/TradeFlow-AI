"""Styling and theme constants for TradeFlow AI dashboard."""

import streamlit as st

# ── Color palette ──
NAVY = "#0F1B2D"
NAVY_LIGHT = "#1A2B45"
BLUE = "#2563EB"
TEAL = "#0D9488"
GREEN = "#16A34A"
ORANGE = "#EA580C"
RED = "#DC2626"
GRAY = "#6B7280"
LIGHT_GRAY = "#F3F4F6"
WHITE = "#FFFFFF"
TEXT_DARK = "#111827"
TEXT_MUTED = "#6B7280"

RISK_COLORS = {
    "Critical": RED,
    "Warning": ORANGE,
    "Healthy": GREEN,
    "Excess": "#7C3AED",  # purple for excess
}

APPROVAL_COLORS = {
    "Pending": ORANGE,
    "Approved": GREEN,
    "Rejected": RED,
}

WAREHOUSE_COLORS = {
    "Dubai": "#2563EB",
    "Abu Dhabi": "#0D9488",
    "Sharjah": "#7C3AED",
}

CATEGORY_COLORS = {
    "Chargers": "#2563EB",
    "Cables": "#0D9488",
    "Computer Accessories": "#EA580C",
    "Storage": "#7C3AED",
    "Peripherals": "#DC2626",
}


def inject_css():
    """Inject custom CSS for a polished, modern look."""
    st.markdown("""
    <style>
    /* ── Global ── */
    .stApp {
        background-color: #F8FAFC;
    }
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 1400px;
    }
    /* Reduce excessive vertical spacing between blocks */
    .stBlock, .stVerticalBlock {
        gap: 0.5rem;
    }
    /* Ensure page titles are fully visible */
    .stMarkdown h1 {
        padding-top: 0.5rem;
        margin-top: 0;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F1B2D 0%, #1A2B45 100%);
    }
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stSelectbox > div > div,
    section[data-testid="stSidebar"] .stRadio label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {
        color: #E2E8F0 !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] h4,
    section[data-testid="stSidebar"] h5,
    section[data-testid="stSidebar"] h6 {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: #2D3F5C;
    }
    /* Sidebar selectbox dropdown options (pop-up list) — dark text on light bg */
    section[data-testid="stSidebar"] .stSelectbox div[role="listbox"] option,
    section[data-testid="stSidebar"] div[data-baseweb="select"] ul li {
        color: #111827 !important;
    }
    /* Sidebar radio button text */
    section[data-testid="stSidebar"] [data-testid="stRadio"] label {
        color: #E2E8F0 !important;
    }

    /* ── KPI cards ── */
    .kpi-card {
        background: white;
        border-radius: 12px;
        padding: 14px 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        border-left: 4px solid var(--accent, #2563EB);
        transition: transform 0.15s;
        overflow: visible;
        white-space: normal;
        word-wrap: break-word;
        margin-bottom: 8px;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    }
    .kpi-label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #6B7280;
        margin-bottom: 6px;
        line-height: 1.3;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .kpi-value {
        font-size: clamp(1.2rem, 2vw, 1.6rem);
        font-weight: 700;
        color: #111827;
        line-height: 1.15;
        white-space: normal;
        word-break: break-word;
        overflow: visible;
    }
    .kpi-sub {
        font-size: 0.7rem;
        color: #9CA3AF;
        margin-top: 4px;
        line-height: 1.3;
        white-space: normal;
        word-break: break-word;
    }

    /* ── Section headers ── */
    .section-header {
        font-size: 1.25rem;
        font-weight: 600;
        color: #111827;
        margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #E5E7EB;
    }

    /* ── Status badges ── */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
    }

    /* ── Agent cards ── */
    .agent-card {
        background: white;
        border-radius: 10px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.07);
        border-top: 3px solid var(--accent, #2563EB);
    }
    .agent-name {
        font-size: 0.95rem;
        font-weight: 600;
        color: #111827;
    }
    .agent-desc {
        font-size: 0.8rem;
        color: #6B7280;
        margin-top: 4px;
    }
    .agent-status {
        font-size: 0.72rem;
        font-weight: 600;
        margin-top: 8px;
    }

    /* ── Chat ── */
    .chat-msg {
        background: white;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .chat-user {
        background: #EFF6FF;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
        text-align: right;
    }

    /* ── Tables ── */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    .stDataFrame [data-testid="stDataFrameResizable"] {
        overflow-x: auto;
    }
    .stDataFrame table thead th {
        background-color: #F3F4F6 !important;
        color: #111827 !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        white-space: nowrap;
    }
    .stDataFrame table tbody td {
        font-size: 0.82rem !important;
        color: #374151 !important;
        white-space: nowrap;
    }

    /* ── Expander styling ── */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 0.9rem;
    }

    /* ── Hide Streamlit branding ── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 20px;
        border-radius: 0;
        font-size: 0.88rem;
    }

    /* ── Responsive breakpoints ── */
    @media (max-width: 768px) {
        .kpi-value {
            font-size: 1.2rem;
            white-space: normal;
        }
        .kpi-label {
            font-size: 0.68rem;
        }
        .section-header {
            font-size: 1.1rem;
        }
    }

    /* ── Selectbox / input readability ── */
    .stSelectbox label,
    .stNumberInput label,
    .stRadio label,
    .stTextInput label {
        font-size: 0.85rem;
        font-weight: 500;
        color: #374151;
    }

    /* ── Warning / info / success text ── */
    .stAlert {
        font-size: 0.88rem;
    }

    /* ── Metric widget (used by st.metric fallback) ── */
    [data-testid="stMetric"] {
        background: white;
        border-radius: 8px;
        padding: 8px 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.78rem;
        color: #374151;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.1rem;
        font-weight: 700;
        color: #111827;
    }
    /* Hide misleading delta arrows on static metrics — only show for real before/after */
    [data-testid="stMetricDelta"] {
        display: none;
    }

    /* ── Alert boxes: ensure readable dark text ── */
    .stAlert {
        color: #111827 !important;
    }
    .stAlert p, .stAlert span, .stAlert li {
        color: #111827 !important;
    }
    [data-testid="stAlertContainer"] {
        color: #111827 !important;
    }
    [data-testid="stAlertContainerInfo"] {
        background-color: #DBEAFE !important;
        border-left: 4px solid #2563EB !important;
    }
    [data-testid="stAlertContainerInfo"] p,
    [data-testid="stAlertContainerInfo"] span {
        color: #1E3A5F !important;
    }
    [data-testid="stAlertContainerSuccess"] {
        background-color: #D1FAE5 !important;
        border-left: 4px solid #16A34A !important;
    }
    [data-testid="stAlertContainerSuccess"] p,
    [data-testid="stAlertContainerSuccess"] span {
        color: #065F46 !important;
    }
    [data-testid="stAlertContainerWarning"] {
        background-color: #FEF3C7 !important;
        border-left: 4px solid #EA580C !important;
    }
    [data-testid="stAlertContainerWarning"] p,
    [data-testid="stAlertContainerWarning"] span {
        color: #78350F !important;
    }
    [data-testid="stAlertContainerError"] {
        background-color: #FEE2E2 !important;
        border-left: 4px solid #DC2626 !important;
    }
    [data-testid="stAlertContainerError"] p,
    [data-testid="stAlertContainerError"] span {
        color: #7F1D1D !important;
    }

    /* ── Expander content text ── */
    .streamlit-expanderHeader,
    details summary span {
        color: #111827 !important;
    }
    .streamlit-expanderContent p,
    .streamlit-expanderContent li,
    .streamlit-expanderContent span {
        color: #374151 !important;
    }

    /* ── Caption / muted text ── */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #4B5563 !important;
    }

    /* ── Markdown text ── */
    .stMarkdown p, .stMarkdown li, .stMarkdown span {
        color: #1F2937;
    }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
    .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
        color: #111827;
    }

    /* ── Plotly chart containers ── */
    .stPlotlyChart, [data-testid="stPlotlyChart"] {
        padding-top: 5px;
    }
    /* Ensure chart titles and legends don't overlap */
    .js-plotly-plot .plotly .gtitle {
        padding-bottom: 8px;
    }
    .js-plotly-plot .plotly .legend {
        margin-top: 10px;
    }

    /* ── Buttons ── */
    .stButton > button {
        font-size: 0.85rem;
        font-weight: 500;
    }

    /* ── Data editor text ── */
    [data-testid="stDataGrid"] {
        color: #111827 !important;
    }

    </style>
    """, unsafe_allow_html=True)


def kpi_card(label, value, sub="", accent="#2563EB"):
    """Render a colorful KPI card with accent-colored left border."""
    st.markdown(
        f"""
        <div class="kpi-card" style="--accent: {accent};">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title):
    """Render a section header with bottom border."""
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)


def agent_card(name, description, status="Ready", accent="#2563EB", activity=""):
    """Render an agent status card with colorful top border."""
    status_icon = "🟢" if status == "Ready" else "🟠" if status == "Running" else "⚪"
    st.markdown(
        f"""
        <div class="agent-card" style="--accent: {accent};">
            <div class="agent-name">{name}</div>
            <div class="agent-desc">{description}</div>
            <div class="agent-status">{status_icon} {status}</div>
            {"<div class='agent-desc' style='margin-top:4px'>" + activity + "</div>" if activity else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(text, color=ORANGE):
    """Render a colored badge using markdown."""
    st.markdown(f"**:orange[{text}]**" if color == ORANGE else f"**{text}**")


def page_title(title, subtitle=""):
    """Render a page title with optional subtitle."""
    st.title(title)
    if subtitle:
        st.caption(subtitle)
