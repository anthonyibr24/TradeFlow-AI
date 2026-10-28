"""Page 2 — AI Demand Forecasting."""

import streamlit as st
import pandas as pd
from components.styling import inject_css, kpi_card, section_header, page_title
from components.charts import (
    forecast_line,
    forecast_with_bounds,
    historical_vs_forecast,
    forecast_all_warehouses,
)
from components.metrics import get_scenario_inventory


def render(data: dict, scenario: str):
    """Render the demand forecasting page."""
    inject_css()
    page_title("AI Demand Forecasting",
               "XGBoost-powered demand predictions across 20 SKUs and 3 warehouses")

    daily_fc = data["daily_forecast"]
    fc_30d = data["forecast_30d"]
    products = data["products"]
    sales = data["sales"]

    # ── Filters ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sku_list = sorted(products["SKU"].tolist())
        sku = st.selectbox("Select SKU", sku_list, index=0)
    with col2:
        categories = sorted(products["Category"].unique().tolist())
        category = st.selectbox("Filter by Category", ["All"] + categories)
    with col3:
        wh_list = sorted(fc_30d["Warehouse"].unique().tolist())
        warehouse = st.selectbox("Select Warehouse", wh_list, index=0)
    with col4:
        period = st.selectbox("Forecast Period", ["30 days", "14 days", "7 days"], index=0)

    period_days = {"30 days": 30, "14 days": 14, "7 days": 7}[period]

    # Filter by category
    if category != "All":
        sku_in_cat = products[products["Category"] == category]["SKU"].tolist()
        sku_options = [s for s in sku_list if s in sku_in_cat]
    else:
        sku_options = sku_list

    # Get product info
    product_info = products[products["SKU"] == sku].iloc[0] if not products[products["SKU"] == sku].empty else None

    # ── Forecast Summary KPIs ──
    fc_row = fc_30d[(fc_30d["SKU"] == sku) & (fc_30d["Warehouse"] == warehouse)]
    if fc_row.empty:
        st.error(f"No forecast data found for {sku} at {warehouse}")
        return

    fc30 = fc_row.iloc[0]
    daily_data = daily_fc[(daily_fc["SKU"] == sku) & (daily_fc["Warehouse"] == warehouse)].sort_values("Date")
    daily_data = daily_data.head(period_days)

    # Compute period-specific totals from daily forecasts
    period_total = float(daily_data["Predicted_Demand"].sum())
    period_avg = float(daily_data["Predicted_Demand"].mean()) if len(daily_data) > 0 else 0
    period_label = f"{period_days}-Day Forecast"

    section_header("Forecast Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_card("SKU", sku, product_info["Product"] if product_info is not None else "", accent="#2563EB")
    with col2:
        kpi_card("Warehouse", warehouse, f"Category: {product_info['Category']}" if product_info is not None else "", accent="#0D9488")
    with col3:
        kpi_card(period_label, f"{period_total:.0f}", f"units — next {period_days} days", accent="#2563EB")
    with col4:
        kpi_card("Avg Daily Demand", f"{period_avg:.1f}", f"based on {period_days}-day forecast", accent="#0D9488")

    # ── Forecast chart ──
    section_header(f"Predicted Demand — Next {period}")
    st.plotly_chart(forecast_line(daily_fc, sku, warehouse, period_days), use_container_width=True, config={"displayModeBar": False})

    # ── Forecast with uncertainty ──
    section_header("Forecast with Uncertainty Bounds")
    st.plotly_chart(forecast_with_bounds(daily_fc, fc30, sku, warehouse), use_container_width=True, config={"displayModeBar": False})
    st.caption("Uncertainty bounds are empirical estimates based on forecast variance, not statistically calibrated confidence intervals.")

    # ── Historical vs Forecast ──
    section_header("Historical Sales vs Forecast Demand")
    st.plotly_chart(historical_vs_forecast(sales, daily_fc, sku, warehouse), use_container_width=True, config={"displayModeBar": False})

    # ── All warehouses comparison ──
    section_header(f"Forecast Across All Warehouses — {sku}")
    st.plotly_chart(forecast_all_warehouses(daily_fc, sku), use_container_width=True, config={"displayModeBar": False})

    # ── Model Information ──
    section_header("Model Information")
    with st.expander("XGBoost Forecasting — Model Details", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Model:** XGBoost (improved with hyperparameter tuning)")
            st.markdown(f"**Selected for {sku}/{warehouse}:** `{fc30['Selected_Model']}`")
            st.markdown("**Training Data:** 90 days of historical sales across 20 SKUs and 3 warehouses")
            st.markdown("**Forecast Horizon:** 30 days (recursive multi-step)")
            st.markdown(f"**Lower Bound:** {fc30['Lower_Bound']:.0f} units")
            st.markdown(f"**Upper Bound:** {fc30['Upper_Bound']:.0f} units")
        with col2:
            st.markdown("**Evaluation:** One-day-ahead validation accuracy (not 30-day recursive accuracy)")
            st.markdown("**Features:** Lag features (1, 7, 14, 28 days), rolling means, day-of-week")
            st.markdown("**Uncertainty:** Heuristic bounds based on forecast variance — not formal confidence intervals")
            st.markdown(f"**Avg Uncertainty Range:** {fc30['Upper_Bound'] - fc30['Lower_Bound']:.0f} units "
                        f"({(fc30['Upper_Bound'] - fc30['Lower_Bound']) / fc30['Forecast_30d'] * 100:.1f}% of forecast)")

        st.markdown("**Key Limitations:**")
        st.markdown("""
        - Forecasts are based on historical patterns and may not capture sudden market shifts.
        - Prediction intervals reflect statistical uncertainty, not operational risk.
        - Accuracy degrades for SKUs with sparse or highly variable sales.
        - Does not account for promotions, supply disruptions, or competitor actions.
        - 30-day aggregate forecasts accumulate daily errors — confidence narrows for longer horizons.
        """)
        st.info("Use forecasts as planning guidance, not certainties. Monitor actual demand vs forecast and retrain periodically.")
