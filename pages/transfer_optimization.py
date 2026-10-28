"""Page 4 — AI Transfer Optimization."""

import streamlit as st
import pandas as pd
from components.styling import (
    inject_css, kpi_card, section_header, page_title,
    APPROVAL_COLORS, BLUE, GREEN, ORANGE, TEAL, RED,
)
from components.charts import (
    transfer_network,
    transfer_bar,
    before_after_comparison,
    economic_impact_chart,
)
from components.metrics import get_opt_summary, get_transfer_recs_df


def render(data: dict, scenario: str, orchestrator=None):
    """Render the transfer optimization page."""
    inject_css()
    page_title("AI Transfer Optimization",
               "MILP-powered inter-warehouse transfer recommendations with economic analysis")

    opt_summary = get_opt_summary(data)
    recs_df = data.get("transfer_recs")

    if scenario != "demonstration" or recs_df is None or recs_df.empty:
        # Original Overstocking scenario — provide business-focused guidance
        section_header("Excess Inventory Overview")
        st.info("""
        **No shortage-driven transfers needed for this scenario.**

        The Original Overstocking scenario has heavy excess inventory and no projected shortages.
        This means:
        - No inter-warehouse transfers are required to prevent stockouts.
        - The focus should be on reducing excess inventory, ageing stock, and holding costs.

        **Opportunities to consider:**
        - Review slow-moving SKUs for potential liquidation or supplier returns.
        - Consolidate stock across warehouses to reduce storage costs.
        - Adjust future purchase orders to align with actual demand patterns.
        - Monitor ageing inventory (61+ days) for obsolescence risk.

        Switch to the **Inventory Imbalance** scenario to see shortage-driven transfer recommendations.
        """)
        return

    # ── Optimization Summary KPIs ──
    section_header("Optimization Summary")
    num_recs = int(opt_summary.get("Number of recommended transfers", 0))
    total_units = int(opt_summary.get("Total units recommended", 0))
    total_cost = float(opt_summary.get("Total transfer cost", 0))
    unmet_before = float(opt_summary.get("Unmet demand before transfers", 0))
    unmet_after = float(opt_summary.get("Unmet demand after transfers", 0))
    unmet_avoided = float(opt_summary.get("Unmet demand avoided", 0))
    margin_preserved = float(opt_summary.get("Estimated margin preserved", 0))
    net_benefit = float(opt_summary.get("Net economic benefit", 0))

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_card("Recommended Transfers", f"{num_recs}", "transfer routes", accent="#2563EB")
    with col2:
        kpi_card("Total Units", f"{total_units:,}", "units to transfer", accent="#0D9488")
    with col3:
        kpi_card("Total Transfer Cost", f"{total_cost:,.0f} AED", "transportation cost", accent="#EA580C")
    with col4:
        kpi_card("Net Economic Benefit", f"{net_benefit:,.0f} AED", "projected benefit", accent="#16A34A")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        kpi_card("Unmet Before", f"{unmet_before:,.0f}", "units of shortage", accent="#DC2626")
    with col6:
        kpi_card("Unmet After", f"{unmet_after:,.0f}", "units remaining", accent="#EA580C")
    with col7:
        kpi_card("Unmet Avoided", f"{unmet_avoided:,.0f}", f"({unmet_avoided/unmet_before*100:.1f}% reduction)", accent="#16A34A")
    with col8:
        kpi_card("Margin Preserved", f"{margin_preserved:,.0f} AED", "projected from simulation", accent="#0D9488")

    # Plain-English summary
    if unmet_before > 0:
        reduction_pct = (unmet_avoided / unmet_before * 100) if unmet_before > 0 else 0
        st.info(f"**Summary:** The optimizer recommends **{num_recs} transfers** ({total_units:,} units) "
                f"to reduce projected shortages from **{unmet_before:,.0f}** to **{unmet_after:,.0f} units** "
                f"({reduction_pct:.1f}% reduction). Projected net economic benefit: **{net_benefit:,.0f} AED** "
                f"(margin preserved {margin_preserved:,.0f} AED − transfer cost {total_cost:,.0f} AED). "
                f"All figures are simulated projections, not realized savings.")

    # ── Before vs After ──
    section_header("Before vs After Optimization")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(before_after_comparison(unmet_before, unmet_after), use_container_width=True, config={"displayModeBar": False})
    with col2:
        st.plotly_chart(economic_impact_chart(total_cost, margin_preserved, net_benefit), use_container_width=True, config={"displayModeBar": False})

    # ── Step 4 Discrepancy Note ──
    with st.expander("📊 Discrepancy Explanation: 98.9% Reduction vs 2/26 Eliminated"):
        st.info("""
        The 98.9% unmet-demand reduction reflects **aggregate units avoided** (1,107.3 / 1,119.7).
        Only **2 of 26** shortage combos were fully eliminated to zero. The remainder were
        significantly reduced but still have small residual unmet demand because transfers
        arrive after lead time, so early-day shortages cannot be prevented. This is expected
        behavior — not a bug.
        """)

    # ── Transfer Recommendations ──
    section_header("Transfer Recommendations")
    products = data["products"]
    prod_map = products.set_index("SKU")["Product"].to_dict()

    # Sort by net benefit (highest first)
    sorted_recs = recs_df.sort_values("Estimated_Net_Benefit_AED", ascending=False).reset_index(drop=True)

    # Top 3 as colorful native Streamlit cards with embedded AI explanation
    top_n = min(3, len(sorted_recs))
    for i in range(top_n):
        rec = sorted_recs.iloc[i]
        sku = rec["SKU"]
        prod_name = prod_map.get(sku, sku)
        accent = BLUE if i == 0 else (TEAL if i == 1 else GREEN)

        # Get product margin for explanation
        prod_row = products[products["SKU"] == sku]
        margin = prod_row.iloc[0]["Profit_Margin_AED"] if not prod_row.empty else 0

        with st.container(border=True):
            st.markdown(f"#### {prod_name} ({sku})")
            st.markdown(f"**{rec['Source_Warehouse']} → {rec['Destination_Warehouse']}**")

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Quantity", f"{int(rec['Transfer_Quantity']):,}", "units")
            with c2:
                st.metric("Delivery Time", f"{int(rec['Lead_Time_Days'])}", "days")
            with c3:
                st.metric("Transfer Cost", f"{rec['Transfer_Cost_AED']:,.0f}", "AED")
            with c4:
                st.metric("Net Benefit", f"{rec['Estimated_Net_Benefit_AED']:,.0f}", "AED")
            st.caption(f"Shortage reduction: {rec['Expected_Unmet_Demand_Avoided']:.0f} units | "
                       f"Approval: {rec.get('Approval_Status', 'Pending')}")

            # Expandable AI explanation inside each card
            with st.expander("Why Did AI Recommend This?", expanded=(i == 0)):
                st.markdown(
                    f"**Source selection:** {rec['Source_Warehouse']} was selected because it holds "
                    f"transferable surplus stock of {prod_name} ({sku}) — inventory above its own "
                    f"forecast demand and safety stock requirements.\n\n"
                    f"**Destination need:** {rec['Destination_Warehouse']} faces a projected "
                    f"shortage of {rec['Expected_Unmet_Demand_Avoided']:.0f} units. Transferring "
                    f"{int(rec['Transfer_Quantity'])} units is expected to reduce this unmet demand.\n\n"
                    f"**Quantity rationale:** The optimizer maximizes shortage reduction while respecting "
                    f"transferable surplus at the source and route capacity.\n\n"
                    f"**Cost-benefit:** Transfer cost: {rec['Transfer_Cost_AED']:.2f} AED. "
                    f"Profit margin: {margin:.2f} AED/unit. "
                    f"Projected margin preserved: {rec['Expected_Unmet_Demand_Avoided'] * margin:.2f} AED. "
                    f"Net benefit: **{rec['Estimated_Net_Benefit_AED']:.2f} AED**.\n\n"
                    f"The transfer arrives in {int(rec['Lead_Time_Days'])} day(s), so shortages occurring "
                    f"before arrival cannot be prevented.\n\n"
                    f"*All figures are projected estimates from simulation, not realized savings.*"
                )

    # All remaining transfers in collapsed expander
    with st.expander(f"View All Transfers ({len(sorted_recs)})", expanded=False):
        display_cols = ["SKU", "Source_Warehouse", "Destination_Warehouse", "Transfer_Quantity",
                        "Lead_Time_Days", "Transfer_Cost_AED", "Expected_Unmet_Demand_Avoided",
                        "Estimated_Net_Benefit_AED", "Approval_Status"]
        display_df = sorted_recs[display_cols].copy()
        display_df.insert(1, "Product", display_df["SKU"].map(prod_map).fillna(display_df["SKU"]))
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)

    # ── Transfer Network ──
    section_header("Warehouse Transfer Network")
    # Convert to agent format for charts
    agent_recs = []
    for _, r in recs_df.iterrows():
        agent_recs.append({
            "sku": r["SKU"],
            "source_warehouse": r["Source_Warehouse"],
            "destination_warehouse": r["Destination_Warehouse"],
            "transfer_quantity": r["Transfer_Quantity"],
            "transfer_cost_aed": r["Transfer_Cost_AED"],
        })
    agent_recs_df = pd.DataFrame(agent_recs)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.plotly_chart(transfer_network(agent_recs_df), use_container_width=True, config={"displayModeBar": False})
    with col2:
        st.plotly_chart(transfer_bar(agent_recs_df), use_container_width=True, config={"displayModeBar": False})

    # Aggregated route summary in expander
    with st.expander("Aggregated Route Summary", expanded=False):
        route_summary = recs_df.groupby(["Source_Warehouse", "Destination_Warehouse"]).agg(
            Total_Units=("Transfer_Quantity", "sum"),
            Total_Cost_AED=("Transfer_Cost_AED", "sum"),
            Count=("Transfer_Quantity", "count"),
        ).reset_index().sort_values("Total_Units", ascending=False)
        st.dataframe(route_summary, use_container_width=True, hide_index=True)
