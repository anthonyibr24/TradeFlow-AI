"""Page 1 — Executive Dashboard."""

import streamlit as st
import pandas as pd
from components.styling import inject_css, kpi_card, section_header, page_title
from components.charts import (
    inventory_by_warehouse,
    risk_distribution_pie,
    risk_distribution_bar,
    warehouse_comparison,
    warehouse_radar,
)
from components.metrics import (
    compute_risk_summary,
    compute_economic_exposure,
    get_opt_summary,
    generate_ai_insights,
    get_scenario_inventory,
    get_scenario_risks,
)
import plotly.graph_objects as go
from components.styling import BLUE, GREEN, ORANGE, RED, TEAL

INSIGHT_ICONS = {
    "warning": "⚠️",
    "info": "ℹ️",
    "money": "💰",
    "alert": "🚨",
    "chart": "📊",
}
INSIGHT_COLORS = {
    "red": RED,
    "orange": ORANGE,
    "blue": BLUE,
    "green": GREEN,
    "teal": TEAL,
    "purple": "#7C3AED",
}


def render(data: dict, scenario: str):
    """Render the executive dashboard page."""
    inject_css()
    page_title("Executive Dashboard",
               f"Complete supply chain overview — {'Demonstration (Inventory Imbalance)' if scenario == 'demonstration' else 'Original (Overstocking)'} scenario")

    # Load data for scenario
    inv_df = get_scenario_inventory(data, scenario)
    forecast_30d = data["forecast_30d"]
    products = data["products"]
    opt_summary = get_opt_summary(data)

    # Compute metrics
    risk = compute_risk_summary(inv_df, forecast_30d)
    economic_exposure = compute_economic_exposure(inv_df, forecast_30d, products)

    # Potential savings from transfers
    potential_savings = opt_summary.get("Net economic benefit", 0) if scenario == "demonstration" else 0

    # ── KPI Cards ──
    section_header("Key Performance Indicators")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_card("Total Available Inventory",
                 f"{risk['total_available']:,.0f}",
                 "units across all warehouses",
                 accent=BLUE)
    with col2:
        kpi_card("Forecast Demand (30d)",
                 f"{risk['total_forecast']:,.0f}",
                 f"coverage ratio {risk['coverage_ratio']:.1f}x",
                 accent=TEAL)
    with col3:
        kpi_card("Critical Inventory Risks",
                 f"{risk['risk_counts'].get('Critical', 0)}",
                 f"SKU-warehouse combos with shortages",
                 accent=RED)
    with col4:
        kpi_card("Excess Inventory",
                 f"{risk['total_excess']:,.0f}",
                 "units above forecast + safety",
                 accent="#7C3AED")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        kpi_card("Expected Unmet Demand",
                 f"{risk['total_unmet']:,.0f}",
                 "units of projected shortages",
                 accent=ORANGE)
    with col6:
        kpi_card("Projected Economic Exposure",
                 f"{economic_exposure:,.0f} AED",
                 "margin at risk from shortages",
                 accent=RED)
    with col7:
        kpi_card("Potential Savings",
                 f"{potential_savings:,.0f} AED",
                 f"from {int(opt_summary.get('Number of recommended transfers', 0))} recommended transfers" if scenario == "demonstration" else "no transfers needed",
                 accent=GREEN)
    with col8:
        risk_count = sum(risk['risk_counts'].values())
        kpi_card("Total SKU-Warehouse Combos",
                 f"{risk_count}",
                 f"{len(products)} SKUs x 3 warehouses",
                 accent=BLUE)

    # ── Charts row 1 ──
    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.plotly_chart(inventory_by_warehouse(inv_df), use_container_width=True, config={"displayModeBar": False})
    with col_right:
        st.plotly_chart(risk_distribution_pie(risk["risk_counts"]), use_container_width=True, config={"displayModeBar": False})

    # ── Charts row 2 ──
    section_header("Warehouse Analysis")
    col1, col2 = st.columns([3, 2])
    with col1:
        st.plotly_chart(warehouse_comparison(inv_df, forecast_30d), use_container_width=True, config={"displayModeBar": False})
    with col2:
        st.plotly_chart(warehouse_radar(inv_df, forecast_30d), use_container_width=True, config={"displayModeBar": False})

    st.plotly_chart(risk_distribution_bar(risk["by_warehouse"]), use_container_width=True, config={"displayModeBar": False})

    # ── Demand Forecast Overview ──
    section_header("Demand Forecast Overview (Next 30 Days)")
    daily_fc = data["daily_forecast"]
    daily_total = daily_fc.groupby("Date")["Predicted_Demand"].sum().reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily_total["Date"], y=daily_total["Predicted_Demand"],
        mode="lines", line=dict(color=BLUE, width=2.5),
        fill="tozeroy", fillcolor="rgba(37,99,235,0.1)",
        hovertemplate="<b>%{x}</b><br>Total demand: %{y:.0f} units<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=30, r=30, t=60, b=30),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Segoe UI", size=14, color="#111827"),
        title=dict(text="Total Daily Demand Forecast Across All SKUs",
                   font=dict(size=16, color="#111827"), x=0.01),
    )
    fig.update_xaxes(gridcolor="#E5E7EB", tickfont=dict(size=12, color="#374151"))
    fig.update_yaxes(gridcolor="#E5E7EB", title="Units", tickfont=dict(size=12, color="#374151"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"Total projected demand over 30 days: {daily_total['Predicted_Demand'].sum():,.0f} units across all SKUs and warehouses. "
               f"Average daily demand: {daily_total['Predicted_Demand'].mean():,.0f} units.")

    # ── AI Insights ──
    section_header("AI-Generated Insights")
    insights = generate_ai_insights(inv_df, forecast_30d, products, opt_summary, scenario)
    for insight in insights:
        icon = INSIGHT_ICONS.get(insight["icon"], "📊")
        with st.container(border=True):
            st.markdown(f"{icon} **{insight['title']}** — {insight['text']}")
