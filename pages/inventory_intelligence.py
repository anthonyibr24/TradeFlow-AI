"""Page 3 — Inventory Intelligence."""

import streamlit as st
import pandas as pd
from components.styling import (
    inject_css, kpi_card, section_header, page_title, RISK_COLORS,
    RED, ORANGE, GREEN, BLUE,
)
from components.charts import (
    ageing_chart,
    ageing_by_sku,
    inventory_projection,
    warehouse_comparison,
    risk_distribution_bar,
)
from components.metrics import (
    get_scenario_inventory,
    get_scenario_risks,
    get_scenario_inbound,
    get_scenario_ageing,
    compute_risk_summary,
)
import math


def render(data: dict, scenario: str):
    """Render the inventory intelligence page."""
    inject_css()
    page_title("Inventory Intelligence",
               "Comprehensive inventory risk analysis with AI-powered explanations")

    inv_df = get_scenario_inventory(data, scenario)
    risks_df = get_scenario_risks(data, scenario)
    forecast_30d = data["forecast_30d"]
    daily_fc = data["daily_forecast"]
    ageing_df = get_scenario_ageing(data, scenario)
    products = data["products"]
    inbound_df = get_scenario_inbound(data, scenario)

    # ── Dependent Filters ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        wh_list = ["All"] + sorted(inv_df["Warehouse"].unique().tolist())
        wh_filter = st.selectbox("Warehouse", wh_list, index=0)
    with col2:
        # Category first (filters SKU options)
        cat_list = ["All"] + sorted(products["Category"].unique().tolist())
        cat_filter = st.selectbox("Category", cat_list, index=0)
    with col3:
        # SKU list depends on selected category
        if cat_filter != "All":
            cat_skus = sorted(
                products[products["Category"] == cat_filter]["SKU"].unique().tolist()
            )
        else:
            cat_skus = sorted(inv_df["SKU"].unique().tolist())
        sku_list = ["All"] + cat_skus
        sku_filter = st.selectbox("SKU", sku_list, index=0)
    with col4:
        risk_list = ["All", "Critical", "Warning", "Healthy", "Excess"]
        risk_filter = st.selectbox("Risk Level", risk_list, index=0)

    # Build merged risk table
    risk_table = inv_df.merge(
        forecast_30d[["SKU", "Warehouse", "Forecast_30d", "Lower_Bound", "Upper_Bound", "Selected_Model"]],
        on=["SKU", "Warehouse"], how="left",
    )
    risk_table["Unmet_Demand"] = (risk_table["Forecast_30d"] - risk_table["Available_Stock"]).clip(lower=0)
    risk_table["Excess_Stock"] = (risk_table["Available_Stock"] - risk_table["Forecast_30d"] - risk_table["Safety_Stock"]).clip(lower=0)
    risk_table["Coverage_Ratio"] = risk_table["Available_Stock"] / risk_table["Forecast_30d"].replace(0, pd.NA)

    def classify(row):
        if row["Unmet_Demand"] > 0:
            return "Critical"
        elif row["Available_Stock"] < row["Safety_Stock"]:
            return "Warning"
        elif row["Excess_Stock"] > 100:
            return "Excess"
        return "Healthy"

    risk_table["Risk_Class"] = risk_table.apply(classify, axis=1)

    # Merge product info
    risk_table = risk_table.merge(products[["SKU", "Product", "Category"]], on="SKU", how="left")

    # Keep an unfiltered copy for the AI explanation lookup
    risk_table_full = risk_table.copy()

    # Apply filters
    if wh_filter != "All":
        risk_table = risk_table[risk_table["Warehouse"] == wh_filter]
    if sku_filter != "All":
        risk_table = risk_table[risk_table["SKU"] == sku_filter]
    if cat_filter != "All":
        risk_table = risk_table[risk_table["Category"] == cat_filter]
    if risk_filter != "All":
        risk_table = risk_table[risk_table["Risk_Class"] == risk_filter]

    # ── Summary KPIs (from filtered data) ──
    section_header("Inventory Risk Summary")
    filtered_counts = risk_table["Risk_Class"].value_counts().to_dict()
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        kpi_card("Total Combos", f"{len(risk_table)}", "filtered", accent="#2563EB")
    with col2:
        kpi_card("Critical", f"{filtered_counts.get('Critical', 0)}", "shortage combos", accent="#DC2626")
    with col3:
        kpi_card("Warning", f"{filtered_counts.get('Warning', 0)}", "below safety stock", accent="#EA580C")
    with col4:
        kpi_card("Excess", f"{filtered_counts.get('Excess', 0)}", "excess stock combos", accent="#7C3AED")
    with col5:
        kpi_card("Healthy", f"{filtered_counts.get('Healthy', 0)}", "well-stocked", accent="#16A34A")

    # ── Risk Table ──
    section_header("Inventory Risk Table")
    display_cols = ["SKU", "Product", "Category", "Warehouse", "Available_Stock", "Safety_Stock",
                    "Forecast_30d", "Unmet_Demand", "Excess_Stock", "Coverage_Ratio", "Risk_Class"]
    display_df = risk_table[display_cols].copy()
    display_df["Coverage_Ratio"] = display_df["Coverage_Ratio"].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")
    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)

    # Risk distribution chart (from filtered data)
    if wh_filter == "All" and len(risk_table) > 0:
        # Build by_warehouse from filtered data
        filtered_by_wh = {}
        for wh in risk_table["Warehouse"].unique():
            wd = risk_table[risk_table["Warehouse"] == wh]
            filtered_by_wh[wh] = {
                "critical": int((wd["Risk_Class"] == "Critical").sum()),
                "warning": int((wd["Risk_Class"] == "Warning").sum()),
                "excess": int((wd["Risk_Class"] == "Excess").sum()),
                "healthy": int((wd["Risk_Class"] == "Healthy").sum()),
            }
        st.plotly_chart(risk_distribution_bar(filtered_by_wh), use_container_width=True, config={"displayModeBar": False})

    # ── Inventory Ageing ──
    section_header("Inventory Ageing Analysis")
    ageing_wh = st.selectbox("Warehouse (Ageing)", ["All"] + sorted(ageing_df["Warehouse"].unique().tolist()), index=0)
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(ageing_chart(ageing_df, ageing_wh), use_container_width=True, config={"displayModeBar": False})
    with col2:
        st.plotly_chart(ageing_by_sku(ageing_df, ageing_wh), use_container_width=True, config={"displayModeBar": False})

    # ── Inventory Projection ──
    section_header("30-Day Inventory Projection")
    proj_sku = st.selectbox("Select SKU for Projection", sorted(inv_df["SKU"].unique().tolist()), index=0, key="proj_sku")
    proj_wh = st.selectbox("Select Warehouse for Projection", sorted(inv_df["Warehouse"].unique().tolist()), index=0, key="proj_wh")

    # Get projection data
    if scenario == "demonstration" and data.get("scenario_projection") is not None:
        proj_df = data["scenario_projection"]
    elif data.get("post_transfer_proj") is not None:
        proj_df = data["post_transfer_proj"]
    else:
        proj_df = data.get("scenario_projection")

    if proj_df is not None:
        # Get safety stock
        safety_row = inv_df[(inv_df["SKU"] == proj_sku) & (inv_df["Warehouse"] == proj_wh)]
        safety = safety_row["Safety_Stock"].values[0] if not safety_row.empty else None

        st.plotly_chart(inventory_projection(proj_df, proj_sku, proj_wh, safety),
                        use_container_width=True, config={"displayModeBar": False})
    else:
        st.warning("Inventory projection data not available.")

    # ── AI Risk Explanation ──
    section_header("AI Risk Explanation")
    explain_sku = st.selectbox("Select SKU for AI Explanation", sorted(inv_df["SKU"].unique().tolist()),
                               index=0, key="explain_sku")
    explain_wh = st.selectbox("Select Warehouse", sorted(inv_df["Warehouse"].unique().tolist()),
                              index=0, key="explain_wh")

    row = risk_table_full[(risk_table_full["SKU"] == explain_sku) & (risk_table_full["Warehouse"] == explain_wh)]
    if not row.empty:
        r = row.iloc[0]
        risk_class = r["Risk_Class"]
        color = RISK_COLORS.get(risk_class, "#6B7280")
        product_name = r.get("Product", explain_sku)

        available = r["Available_Stock"]
        safety = r["Safety_Stock"]
        forecast = r["Forecast_30d"]
        unmet = r["Unmet_Demand"]
        excess = r["Excess_Stock"]
        coverage = r["Coverage_Ratio"] if not pd.isna(r["Coverage_Ratio"]) else 0

        # Product and Warehouse
        with st.container(border=True):
            st.markdown(f"#### {product_name} ({explain_sku}) — {explain_wh}")

            # Inventory Status badge
            badge_icon = {"Critical": "🔴", "Warning": "🟠", "Excess": "🟣", "Healthy": "🟢"}.get(risk_class, "⚪")
            st.markdown(f"##### {badge_icon} Inventory Status: **{risk_class}**")

        # Why This Status — three KPI cards
        st.markdown("**Why This Status?**")
        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            kpi_card("Available Inventory", f"{available:,.0f}", "units in stock", accent=BLUE)
        with col_e2:
            kpi_card("Forecast Demand (30d)", f"{forecast:,.0f}", "units projected", accent=BLUE)
        with col_e3:
            if unmet > 0:
                kpi_card("Shortage", f"{unmet:,.0f}", "units unmet", accent=RED)
            elif excess > 0:
                kpi_card("Excess Stock", f"{excess:,.0f}", "units above need", accent="#7C3AED")
            else:
                kpi_card("Surplus", f"{available - forecast:,.0f}", "units above forecast", accent=GREEN)

        # Recommended Action
        st.markdown("**Recommended Action**")
        if risk_class == "Critical":
            st.warning("Evaluate inter-warehouse transfers to reduce the projected shortage.")
        elif risk_class == "Warning":
            st.info("Monitor closely and consider early replenishment before stock drops below safety level.")
        elif risk_class == "Excess":
            st.info("Consider transferring excess to shortage locations or liquidating aged stock.")
        else:
            st.success("No action needed. Continue normal monitoring.")

        # ── Actual Transfer Recommendations from Optimizer ──
        recs_df = data.get("transfer_recs")
        if recs_df is not None and not recs_df.empty:
            # Find transfers involving this SKU and warehouse
            outgoing = recs_df[(recs_df["SKU"] == explain_sku) & (recs_df["Source_Warehouse"] == explain_wh)]
            incoming = recs_df[(recs_df["SKU"] == explain_sku) & (recs_df["Destination_Warehouse"] == explain_wh)]

            if not outgoing.empty or not incoming.empty:
                section_header("Optimizer Transfer Recommendations")
                st.markdown(f"**{product_name} ({explain_sku}) at {explain_wh}** is involved in the following "
                            f"MILP-optimized transfer recommendations:")

                if not outgoing.empty:
                    st.markdown("#### Outgoing Transfers (Source)")
                    for _, tr in outgoing.iterrows():
                        with st.container(border=True):
                            st.markdown(f"**{product_name} ({explain_sku})**")
                            st.markdown(f"**{explain_wh} → {tr['Destination_Warehouse']}**")
                            c1, c2, c3, c4 = st.columns(4)
                            with c1:
                                st.metric("Quantity", f"{int(tr['Transfer_Quantity']):,}", "units")
                            with c2:
                                st.metric("Delivery Time", f"{int(tr['Lead_Time_Days'])}", "days")
                            with c3:
                                st.metric("Transfer Cost", f"{tr['Transfer_Cost_AED']:,.0f}", "AED")
                            with c4:
                                st.metric("Net Benefit", f"{tr['Estimated_Net_Benefit_AED']:,.0f}", "AED")
                            st.caption(f"Shortage reduction: {tr['Expected_Unmet_Demand_Avoided']:.0f} units | "
                                       f"Approval: {tr.get('Approval_Status', 'Pending')}")

                if not incoming.empty:
                    st.markdown("#### Incoming Transfers (Destination)")
                    for _, tr in incoming.iterrows():
                        with st.container(border=True):
                            st.markdown(f"**{product_name} ({explain_sku})**")
                            st.markdown(f"**{tr['Source_Warehouse']} → {explain_wh}**")
                            c1, c2, c3, c4 = st.columns(4)
                            with c1:
                                st.metric("Quantity", f"{int(tr['Transfer_Quantity']):,}", "units")
                            with c2:
                                st.metric("Delivery Time", f"{int(tr['Lead_Time_Days'])}", "days")
                            with c3:
                                st.metric("Transfer Cost", f"{tr['Transfer_Cost_AED']:,.0f}", "AED")
                            with c4:
                                st.metric("Net Benefit", f"{tr['Estimated_Net_Benefit_AED']:,.0f}", "AED")
                            st.caption(f"Shortage reduction: {tr['Expected_Unmet_Demand_Avoided']:.0f} units | "
                                       f"Approval: {tr.get('Approval_Status', 'Pending')}")
            else:
                st.caption(f"No optimizer transfer recommendations involve {product_name} ({explain_sku}) at {explain_wh} "
                           f"under the current optimization conditions.")

        # Technical Details expander
        with st.expander("Technical Details", expanded=False):
            st.markdown(f"**Coverage Ratio:** {coverage:.2f}x (target: ≥1.0x)")
            st.markdown(f"**Safety Stock:** {safety:,.0f} units")
            if unmet > 0:
                pct = (unmet / forecast * 100) if forecast > 0 else 0
                st.markdown(f"**Unmet as % of forecast:** {pct:.0f}%")
                st.markdown(f"- Available stock ({available:,.0f} units) is insufficient to cover 30-day forecast ({forecast:,.0f} units).")
                st.markdown(f"- Projected unmet demand: **{unmet:,.0f} units**.")
                st.markdown("- This shortage will result in lost sales and potential customer churn.")
            elif excess > 0:
                st.markdown(f"- Excess inventory: **{excess:,.0f} units** above forecast + safety stock.")
                st.markdown("- Capital tied up in slow-moving inventory with holding costs.")
            elif available < safety:
                st.markdown(f"- Available stock ({available:,.0f}) below safety stock ({safety:,.0f}).")
                st.markdown("- If demand exceeds forecast, stockouts may occur before replenishment.")
            else:
                st.markdown(f"- Coverage ratio: {coverage:.2f}x — above safety stock threshold.")
                st.markdown("- No immediate action needed.")
    else:
        st.info(f"No data found for {explain_sku} at {explain_wh}.")


def _generate_risk_explanation(row, sku, warehouse, products):
    """Generate a deterministic risk explanation — kept for backward compatibility."""
    risk_class = row["Risk_Class"]
    available = row["Available_Stock"]
    safety = row["Safety_Stock"]
    forecast = row["Forecast_30d"]
    unmet = row["Unmet_Demand"]
    excess = row["Excess_Stock"]
    coverage = row["Coverage_Ratio"]
    product_name = row.get("Product", sku)

    if risk_class == "Critical":
        explanation = f"""
**{product_name} ({sku}) at {warehouse}** is classified as **Critical** because:

- Available stock ({available:,.0f} units) is **insufficient** to cover the 30-day forecast demand ({forecast:,.0f} units).
- Projected unmet demand: **{unmet:,.0f} units** — meaning {unmet / forecast * 100:.0f}% of forecast demand cannot be fulfilled.
- Coverage ratio: {coverage:.2f}x (target: ≥1.0x).
- This shortage will result in lost sales and potential customer churn.

**Recommended Action:** Evaluate inter-warehouse transfers to reduce the projected shortage.
"""
    elif risk_class == "Warning":
        explanation = f"""
**{product_name} ({sku}) at {warehouse}** is classified as **Warning** because:

- Available stock ({available:,.0f} units) is **below safety stock** ({safety:,.0f} units).
- While no immediate shortage is projected, the inventory buffer is insufficient.
- If demand exceeds forecast, stockouts may occur before replenishment arrives.

**Recommended Action:** Monitor closely and consider early replenishment.
"""
    elif risk_class == "Excess":
        explanation = f"""
**{product_name} ({sku}) at {warehouse}** is classified as **Excess** because:

- Available stock ({available:,.0f} units) significantly exceeds the 30-day forecast demand ({forecast:,.0f} units).
- Excess inventory: **{excess:,.0f} units** above forecast + safety stock.
- This represents capital tied up in slow-moving inventory with holding costs.

**Recommended Action:** Consider transferring excess to shortage locations or liquidating aged stock.
"""
    else:
        explanation = f"""
**{product_name} ({sku}) at {warehouse}** is classified as **Healthy** because:

- Available stock ({available:,.0f} units) adequately covers the 30-day forecast demand ({forecast:,.0f} units).
- Coverage ratio: {coverage:.2f}x — above safety stock threshold.
- No immediate action needed.

**Recommended Action:** Continue normal monitoring.
"""
    return explanation
