"""Demand Uncertainty Analysis page.

Shows how forecast uncertainty affects inventory risk, transfer optimization,
and projected economic benefit across three demand scenarios:
  - Low Demand (forecast - sigma_30d)
  - Expected Demand (unchanged XGBoost forecast)
  - High Demand (forecast + sigma_30d)

All results come from actual backend calculations — no hardcoded values.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os

from components.styling import (
    inject_css, kpi_card, section_header, page_title,
    BLUE, GREEN, ORANGE, RED, TEAL, GRAY,
)
from components.charts import _apply_layout
from demand_uncertainty import run_demand_uncertainty_analysis


def render(data: dict, scenario: str):
    """Render the Demand Uncertainty Analysis page.

    Parameters
    ----------
    data : dict — data loaded by load_data()
    scenario : str — "demonstration" or "original"
    """
    inject_css()
    page_title(
        "Demand Uncertainty Analysis",
        f"Scenario: {scenario.capitalize()} | "
        "How forecast uncertainty affects shortages, transfers, and economic benefit"
    )

    # Resolve data directory
    data_dir = st.session_state.get("data_dir") or os.environ.get("TRADEFLOW_DATA_DIR")
    if not data_dir:
        st.warning("Data directory not found. Demand Uncertainty Analysis unavailable.")
        return

    # ── Run analysis (cached in session state) ──
    cache_key = f"uncertainty_{scenario}"
    if cache_key not in st.session_state:
        with st.spinner("Running demand uncertainty analysis... Rerunning MILP optimizer for 3 scenarios."):
            st.session_state[cache_key] = run_demand_uncertainty_analysis(data_dir, scenario)

    result = st.session_state[cache_key]
    u = result["uncertainty"]

    # ════════════════════════════════════════════════════════════
    # A. UNCERTAINTY METHOD EXPLANATION
    # ════════════════════════════════════════════════════════════
    section_header("What Is Demand Uncertainty?")

    st.info("""
    **Demand uncertainty** means the actual demand may differ from what AI predicts. We test three scenarios:

    - **Low Demand:** Customers buy less than predicted (forecast minus uncertainty)
    - **Expected Demand:** Customers buy approximately what AI predicts (unchanged forecast)
    - **High Demand:** Customers buy more than predicted (forecast plus uncertainty)

    For each scenario, the system recalculates shortages, recommended transfers, and projected economic benefit.
    """)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_card("Daily Residual Std", f"{u['sigma_daily']:.2f}", "units (from test set)", accent=BLUE)
    with col2:
        kpi_card("30-Day Uncertainty", f"{u['sigma_30d']:.2f}", "sigma_daily x sqrt(30)", accent=ORANGE)
    with col3:
        kpi_card("Test Residuals", f"{u['n_residuals']}", "out-of-sample predictions", accent=TEAL)
    with col4:
        kpi_card("Daily MAE", f"{u['mae_daily']:.2f}", "mean absolute error", accent=GRAY)

    with st.expander("Technical Details — How Uncertainty Is Calculated", expanded=False):
        st.markdown(f"""
        {u['method_description']}

        **Three scenarios (per SKU-warehouse):**
        - **Low Demand:** Forecast_30d − {u['sigma_30d']:.2f} units (floored at 0)
        - **Expected Demand:** Forecast_30d (unchanged XGBoost forecast)
        - **High Demand:** Forecast_30d + {u['sigma_30d']:.2f} units

        For each scenario, the system reruns:
        1. Inventory risk calculation (shortage, excess, classification)
        2. Daily inventory simulation (30-day projection)
        3. MILP transfer optimization (scipy.optimize.milp)
        4. Transfer cost and projected net benefit calculation

        **Important:** These bounds are **empirical sensitivity estimates**, not statistically
        calibrated prediction intervals. The i.i.d. assumption likely understates true uncertainty.
        """)

    # ════════════════════════════════════════════════════════════
    # B. SCENARIO COMPARISON
    # ════════════════════════════════════════════════════════════
    section_header("Scenario Comparison")

    comp_df = pd.DataFrame(result["comparison_table"])

    # Color-coded scenario summary rows
    scenario_colors = [BLUE, TEAL, ORANGE]
    scenario_icons = ["📉", "📊", "📈"]
    for i in range(3):
        row = comp_df.loc[i]
        accent = scenario_colors[i]
        icon = scenario_icons[i]
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card(f"{icon} Forecast Demand", f"{row['Forecast Demand']:,.0f}", row["Scenario"], accent=accent)
        with c2:
            kpi_card("Recommended Transfers", f"{row['Recommended Transfers']}", f"{row['Units Transferred']:,} units", accent=accent)
        with c3:
            kpi_card("Remaining Shortages", f"{row['Unmet After Transfers']:,.1f}", "after transfers", accent=accent)
        with c4:
            kpi_card("Net Benefit", f"{row['Net Benefit (AED)']:,.0f}", "AED (projected)", accent=accent)

    with st.expander("Detailed Comparison Table", expanded=False):
        st.dataframe(comp_df, use_container_width=True, hide_index=True)
    st.caption("All values come from actual backend calculations. "
               "The MILP optimizer is rerun for each demand scenario.")

    # ════════════════════════════════════════════════════════════
    # C. VISUALIZATIONS
    # ════════════════════════════════════════════════════════════
    section_header("Visualizations")

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        # Demand uncertainty chart
        fig_demand = go.Figure()
        scenarios = ["Low Demand", "Expected Demand", "High Demand"]
        colors = [BLUE, TEAL, ORANGE]
        forecast_vals = [comp_df.loc[i, "Forecast Demand"] for i in range(3)]

        fig_demand.add_trace(go.Bar(
            x=scenarios,
            y=forecast_vals,
            marker_color=colors,
            text=[f"{v:,.0f}" for v in forecast_vals],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Forecast: %{y:,.0f} units<extra></extra>",
        ))
        fig_demand = _apply_layout(fig_demand, "Total Demand Forecast by Scenario")
        fig_demand.update_yaxes(title="Units")
        st.plotly_chart(fig_demand, use_container_width=True, config={"displayModeBar": False})

    with col_chart2:
        # Projected shortage comparison
        all_unmet_zero = all(comp_df.loc[i, "Unmet Before Transfers"] < 0.1 for i in range(3))

        if all_unmet_zero:
            st.info("No projected shortages under any tested demand scenario. "
                    "Inventory levels are sufficient across all scenarios.")
        else:
            fig_shortage = go.Figure()
            unmet_before = [comp_df.loc[i, "Unmet Before Transfers"] for i in range(3)]
            unmet_after = [comp_df.loc[i, "Unmet After Transfers"] for i in range(3)]

            fig_shortage.add_trace(go.Bar(
                x=scenarios, y=unmet_before, name="Before Transfers",
                marker_color=RED, text=[f"{v:,.0f}" for v in unmet_before],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Before: %{y:,.1f} units<extra></extra>",
            ))
            fig_shortage.add_trace(go.Bar(
                x=scenarios, y=unmet_after, name="After Transfers",
                marker_color=GREEN, text=[f"{v:,.0f}" for v in unmet_after],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>After: %{y:,.1f} units<extra></extra>",
            ))
            fig_shortage = _apply_layout(fig_shortage, "Projected Unmet Demand by Scenario")
            fig_shortage.update_yaxes(title="Units")
            fig_shortage.update_layout(barmode="group", legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig_shortage, use_container_width=True, config={"displayModeBar": False})

    # Economic benefit comparison
    all_benefit_zero = all(comp_df.loc[i, "Net Benefit (AED)"] < 0.1 for i in range(3))

    if all_benefit_zero:
        st.info("No shortage-driven transfer costs or economic benefits under any tested demand scenario.")
    else:
        fig_benefit = go.Figure()
        net_benefits = [comp_df.loc[i, "Net Benefit (AED)"] for i in range(3)]
        transfer_costs = [comp_df.loc[i, "Transfer Cost (AED)"] for i in range(3)]

        fig_benefit.add_trace(go.Bar(
            x=scenarios, y=net_benefits, name="Net Benefit",
            marker_color=GREEN, text=[f"{v:,.0f}" for v in net_benefits],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Net Benefit: %{y:,.0f} AED<extra></extra>",
        ))
        fig_benefit.add_trace(go.Bar(
            x=scenarios, y=transfer_costs, name="Transfer Cost",
            marker_color=ORANGE, text=[f"{v:,.0f}" for v in transfer_costs],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Cost: %{y:,.0f} AED<extra></extra>",
        ))
        fig_benefit = _apply_layout(fig_benefit, "Economic Impact by Scenario")
        fig_benefit.update_yaxes(title="AED")
        fig_benefit.update_layout(barmode="group", legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig_benefit, use_container_width=True, config={"displayModeBar": False})

    # ════════════════════════════════════════════════════════════
    # D. INTERACTIVE SCENARIO SELECTION
    # ════════════════════════════════════════════════════════════
    section_header("Interactive Scenario Selection")

    selected_scenario = st.radio(
        "Select a demand scenario to view transfer recommendations:",
        options=["Low Demand", "Expected Demand", "High Demand"],
        horizontal=True,
    )

    scenario_key = selected_scenario.lower().replace(" demand", "")
    sc_result = result["scenarios"][scenario_key]
    opt = sc_result["optimization"]
    risk = sc_result["risk"]

    # KPIs for selected scenario
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    with col_k1:
        kpi_card("Forecast Demand", f"{risk['total_forecast']:,.0f}", "units", accent=BLUE)
    with col_k2:
        kpi_card("Unmet (Before)", f"{opt['baseline_unmet']:,.1f}", "units (dynamic sim)", accent=RED)
    with col_k3:
        kpi_card("Unmet (After)", f"{opt['post_transfer_unmet']:,.1f}", "units", accent=ORANGE)
    with col_k4:
        kpi_card("Net Benefit", f"{opt['net_economic_benefit']:,.2f}", "AED (projected)", accent=GREEN)

    # Transfer recommendations for selected scenario
    recs = opt["recommendations"]
    if recs:
        rec_df = pd.DataFrame(recs)

        with st.expander(f"Transfer Recommendations for {selected_scenario} ({len(recs)} transfers)", expanded=False):
            display_cols = ["sku", "source_warehouse", "destination_warehouse",
                            "transfer_quantity", "lead_time_days", "transfer_cost_aed",
                            "expected_unmet_avoided", "estimated_net_benefit_aed"]
            available_cols = [c for c in display_cols if c in rec_df.columns]

            if available_cols:
                display_recs = rec_df[available_cols].copy()
                display_recs.columns = [c.replace("_", " ").title() for c in available_cols]
                st.dataframe(display_recs, use_container_width=True, hide_index=True)

            st.caption(f"{len(recs)} recommended transfers for {selected_scenario}. "
                       f"Total: {opt['total_units']:,} units, {opt['transfer_cost']:,.2f} AED cost. "
                       "All values from actual MILP optimization.")
    else:
        st.info(f"No transfer recommendations for {selected_scenario}.")

    # ════════════════════════════════════════════════════════════
    # E. ROBUST DECISION ANALYSIS
    # ════════════════════════════════════════════════════════════
    section_header("Robust Decision Analysis")

    exp_opt = result["scenarios"]["expected"]["optimization"]
    high_opt = result["scenarios"]["high"]["optimization"]

    exp_recs = exp_opt["num_recommendations"]
    high_recs = high_opt["num_recommendations"]

    # Extract the three distinct robustness values from the cross-scenario evaluation.
    # These are computed by evaluate_plan_under_different_demand() in demand_uncertainty.py
    # — NOT hardcoded.
    rob = result["robustness"]
    exp_plan_exp_unmet = rob["exp_plan_under_exp_unmet"]   # expected plan, expected demand
    exp_plan_high_unmet = rob["exp_plan_under_high_unmet"]  # expected plan, high demand
    high_plan_high_unmet = rob["high_plan_under_high_unmet"]  # high plan, high demand
    high_baseline_unmet = rob["high_baseline_unmet"]          # high demand, no transfers
    additional_recs = high_recs - exp_recs

    # KPI cards: three distinct evaluation results
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        kpi_card("Expected-Plan under Expected Demand",
                 f"{exp_plan_exp_unmet:.1f}",
                 "units — plan matches demand", accent=GREEN)
    with col_r2:
        kpi_card("Expected-Plan under High Demand",
                 f"{exp_plan_high_unmet:.1f}",
                 "units — plan stressed by high demand" if exp_plan_high_unmet > 0.1
                 else "units — sufficient under high demand",
                 accent=ORANGE if exp_plan_high_unmet > 0.1 else GREEN)
    with col_r3:
        kpi_card("High-Demand Plan under High Demand",
                 f"{high_plan_high_unmet:.1f}",
                 "units — optimized for high demand" if high_plan_high_unmet > 0.1
                 else "units — sufficient under high demand",
                 accent=RED if high_plan_high_unmet > 0.1 else GREEN)

    # Dynamic robustness explanation based on actual values
    all_zero = (exp_plan_exp_unmet < 0.1 and exp_plan_high_unmet < 0.1 and high_plan_high_unmet < 0.1)

    if all_zero:
        st.info("""
        **Inventory Sufficient Across All Demand Scenarios.**
        No shortage-driven transfers are required under any tested scenario.
        """)
    else:
        if exp_plan_high_unmet > 0.1:
            st.warning(f"""
            **Expected-demand plan is NOT robust under high demand.**
            Applying the expected-demand transfer plan to the high-demand scenario leaves
            **{exp_plan_high_unmet:.1f} units** unmet, versus {high_plan_high_unmet:.1f} units
            with the high-demand-optimized plan ({additional_recs} additional transfers needed).
            """)
        else:
            st.success("**Expected-demand plan is robust** under all tested demand scenarios.")

    # Detailed comparison table in expander
    with st.expander("Robustness Check — Detailed Comparison", expanded=False):
        if all_zero:
            st.markdown(f"""
            All three evaluations produce zero post-transfer unmet demand:

            | Evaluation | Transfers | Post-Transfer Unmet |
            |---|---|---|
            | Expected-demand plan under expected demand | {exp_recs} | **{exp_plan_exp_unmet:.1f}** units |
            | Expected-demand plan under high demand | {exp_recs} | **{exp_plan_high_unmet:.1f}** units |
            | High-demand plan under high demand | {high_recs} | **{high_plan_high_unmet:.1f}** units |

            Inventory remains sufficient across all tested demand scenarios.
            No shortage-driven transfers are required.

            **Note:** All values are computed dynamically from actual backend simulations.
            """)
        else:
            st.markdown(f"""
            | Evaluation | Transfers | Post-Transfer Unmet |
            |---|---|---|
            | Expected-demand plan **under expected demand** | {exp_recs} | **{exp_plan_exp_unmet:.1f}** units |
            | Expected-demand plan **under high demand** | {exp_recs} | **{exp_plan_high_unmet:.1f}** units |
            | High-demand plan **under high demand** | {high_recs} | **{high_plan_high_unmet:.1f}** units |

            If the expected-demand transfer plan ({exp_recs} transfers) were applied to the high-demand
            scenario, the post-transfer unmet demand would be **{exp_plan_high_unmet:.1f} units** —
            compared to only {high_plan_high_unmet:.1f} units when the high-demand-optimized plan
            ({high_recs} transfers) is used. The expected plan leaves an additional
            **{exp_plan_high_unmet - high_plan_high_unmet:.1f} units** unmet under high demand because
            it doesn't include the {additional_recs} additional transfers that the high-demand scenario
            requires. The high-demand baseline (no transfers) is {high_baseline_unmet:.1f} units.

            This is NOT a robust optimization — it's a comparison of two separate optimizations
            plus a cross-scenario simulation. All values are computed dynamically from actual backend simulations.
            """)

    # ════════════════════════════════════════════════════════════
    # F. EXPLANATION PANEL (in expander for optional detail)
    # ════════════════════════════════════════════════════════════
    with st.expander("Why Demand Forecasts Are Uncertain", expanded=False):
        st.markdown("""
        **Sources of forecast error:**

        - **Demand variability:** Day-to-day fluctuations in customer orders
        - **Trend changes:** Upward or downward shifts not captured in training data
        - **Seasonality:** Weekly/monthly patterns that may shift
        - **External shocks:** Promotions, competitor actions, supply disruptions
        - **Model limitations:** XGBoost captures patterns but cannot predict random events

        **How uncertainty affects shortages:**

        When demand exceeds the forecast (high-demand scenario), more SKU-warehouse combinations
        face shortages. The optimizer may recommend more transfers, increasing both transfer cost
        and projected net benefit.

        **Limitations of the uncertainty method:**

        - The i.i.d. residual assumption likely understates true 30-day uncertainty
        - Test residuals cover only 15 days; the 30-day forecast horizon is longer
        - These are **empirical sensitivity bounds**, not statistically calibrated prediction intervals
        """)

    st.caption("Interactive simulation — no physical inventory changes. "
               "All results are projected estimates from actual backend calculations.")

    # ════════════════════════════════════════════════════════════
    # G. BUSINESS INTERPRETATION
    # ════════════════════════════════════════════════════════════
    section_header("What Does This Mean for the Business?")

    low_opt = result["scenarios"]["low"]["optimization"]
    high_opt = result["scenarios"]["high"]["optimization"]

    # Build dynamic explanation
    if all_zero:
        st.info(f"""
        **All demand scenarios are covered by current inventory.**

        - **If demand is lower than expected:** No shortages. Excess inventory may increase.
          Consider reducing future purchase orders for slow-moving SKUs.

        - **If demand matches the forecast:** No shortages. No transfers needed.

        - **If demand is higher than expected:** No shortages under the tested high-demand
          scenario. Current inventory provides a comfortable buffer.

        **Recommendation:** No shortage-driven transfers are required under any tested scenario.
        Focus on managing excess inventory and optimizing stock levels for cost efficiency.
        """)
    else:
        low_recs_count = low_opt["num_recommendations"]
        high_recs_count = high_opt["num_recommendations"]
        exp_recs_count = exp_recs
        high_net = high_opt["net_economic_benefit"]
        exp_net = exp_opt["net_economic_benefit"]

        st.info(f"""
        **If demand is lower than expected:** {low_recs_count} transfers recommended,
        {low_opt['total_units']:,} units. Net benefit: {low_opt['net_economic_benefit']:,.0f} AED.

        **If demand matches the forecast:** {exp_recs_count} transfers recommended,
        {exp_opt['total_units']:,} units. Net benefit: {exp_net:,.0f} AED.

        **If demand is higher than expected:** {high_recs_count} transfers recommended,
        {high_opt['total_units']:,} units. Net benefit: {high_net:,.0f} AED.

        **Transfer recommendations change with demand:** The optimizer adjusts both the number
        of transfers and the quantities moved. {"More transfers are needed under high demand."
        if high_recs_count > exp_recs_count else "Transfer counts are similar across scenarios."}

        **Is the expected-demand plan sufficient under high demand?**
        {"No." if exp_plan_high_unmet > 0.1 else "Yes."} The expected-demand transfer plan leaves
        {exp_plan_high_unmet:.1f} units unmet under the high-demand scenario.{""
        if exp_plan_high_unmet < 0.1 else f" The high-demand-optimized plan reduces this to "
        f"{high_plan_high_unmet:.1f} units."}

        **Recommendation:** {"Consider preparing contingency transfers for high-demand scenarios." if exp_plan_high_unmet > 0.1
        else "Current planning covers all tested scenarios adequately."}
        """)
