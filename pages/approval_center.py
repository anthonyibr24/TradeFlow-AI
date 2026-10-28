"""Page 6 — Human Approval Center."""

import streamlit as st
import pandas as pd
from datetime import datetime
from components.styling import (
    inject_css, kpi_card, section_header, page_title,
    APPROVAL_COLORS, GREEN, ORANGE, RED, BLUE,
)
from components.charts import approval_impact_chart
from components.metrics import compute_approved_plan_impact


def render(data: dict, scenario: str, orchestrator=None):
    """Render the approval center page."""
    inject_css()
    page_title("Human Approval Center",
               "Review, approve, or reject transfer recommendations — all decisions persist in SQLite")

    if orchestrator is None:
        st.error("Orchestrator not initialized. Cannot manage approvals.")
        return

    # ── Ensure recommendations are loaded ──
    all_recs = orchestrator.approval_agent.get_all_approvals(scenario=scenario)
    if not all_recs:
        if scenario == "demonstration":
            with st.spinner("Loading transfer recommendations into approval system..."):
                opt_result = orchestrator.get_transfer_recommendations(scenario, force_reload=True)
                all_recs = orchestrator.approval_agent.get_all_approvals(scenario=scenario)
        else:
            st.info("""
            No transfer recommendations for the original scenario. The original scenario has
            no projected shortages, so no transfers are needed. Switch to the **Demonstration**
            scenario to manage approvals.
            """)
            return

    if not all_recs:
        st.warning("No recommendations available. Run the optimization first.")
        return

    # ── Summary KPIs ──
    plan_impact = compute_approved_plan_impact(orchestrator, scenario, all_recs)

    section_header("Approval Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_card("Total Recommendations", f"{plan_impact['total_count']}", "transfers proposed", accent=BLUE)
    with col2:
        kpi_card("Pending", f"{plan_impact['pending_count']}", "awaiting decision", accent=ORANGE)
    with col3:
        kpi_card("Approved", f"{plan_impact['approved_count']}", f"{plan_impact['approved_units']} units", accent=GREEN)
    with col4:
        kpi_card("Rejected", f"{plan_impact['rejected_count']}", "transfers rejected", accent=RED)

    # ── Impact comparison ──
    section_header("Proposed vs Approved Plan Impact")

    approved_benefit = plan_impact["approved_benefit"]
    total_proposed = plan_impact["total_proposed_benefit"]
    optimizer_net = plan_impact["optimizer_net_economic_benefit"]
    pct = (approved_benefit / total_proposed * 100) if total_proposed > 0 else 0

    # Three colorful KPI cards
    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        kpi_card("Total Proposed Benefit", f"{total_proposed:,.0f} AED",
                 "sum of individual transfer benefits", accent=BLUE)
    with col_a2:
        kpi_card("Approved Benefit", f"{approved_benefit:,.0f} AED",
                 f"{plan_impact['approved_units']:,} units approved", accent=GREEN)
    with col_a3:
        kpi_card("Approval Progress", f"{pct:.1f}%",
                 f"{plan_impact['approved_cost']:,.0f} AED transfer cost", accent=ORANGE)

    # Progress bar
    st.progress(pct / 100.0 if total_proposed > 0 else 0.0)

    # Chart + approved plan details
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            approval_impact_chart(
                plan_impact["total_proposed_benefit"],
                plan_impact["approved_benefit"],
                plan_impact["rejected_benefit"],
                plan_impact["pending_benefit"],
            ),
            use_container_width=True, config={"displayModeBar": False},
        )
    with col2:
        pct_of_optimizer = (approved_benefit / optimizer_net * 100) if optimizer_net > 0 else 0
        with st.container(border=True):
            st.markdown("#### Approved-Plan Impact")
            st.metric("Approved Benefit", f"{approved_benefit:,.0f} AED",
                      f"{pct:.1f}% of proposed ({total_proposed:,.0f} AED)")
            st.caption(f"{pct_of_optimizer:.1f}% of optimizer's simulated net benefit ({optimizer_net:,.0f} AED)")
            st.metric("Approved Units", f"{plan_impact['approved_units']:,} units")
            st.metric("Approved Transfer Cost", f"{plan_impact['approved_cost']:,.0f} AED")
            st.metric("Unmet Demand Avoided", f"{plan_impact['approved_unmet_avoided']:,.0f} units")

    # How Benefits Are Calculated expander
    with st.expander("How Benefits Are Calculated", expanded=False):
        st.markdown("""
        **Important distinction — two different benefit metrics:**

        | Metric | Value | How Calculated |
        |---|---|---|
        | **Sum of individual transfer benefits** | Sum of each transfer's `estimated_net_benefit_aed` | Simple arithmetic sum; does not account for transfer interactions |
        | **Optimizer's simulated net benefit** | From post-transfer daily inventory simulation | Accounts for lead-time effects, inbound arrivals, and demand fulfillment dynamics |

        The percentage above uses the **sum of individual transfer benefits** as the denominator,
        not the optimizer's simulated net benefit. These two values differ because the simulation
        credits margin for all demand fulfilled (including demand covered by inbound orders),
        while individual estimates only credit the `reducible_unmet` portion per transfer.

        - **Approved-plan impact** includes ONLY approved transfers.
        - **Actual operational impact** is unavailable because this is a simulation.
        """)

    # ── Pending Approvals ──
    section_header("Pending Transfer Recommendations")
    pending_recs = [r for r in all_recs if r["approval_status"] == "Pending"]

    if not pending_recs:
        st.success("No pending recommendations. All transfers have been reviewed.")
    else:
        st.markdown(f"**{len(pending_recs)}** transfers awaiting your decision.")

        products = data["products"]
        prod_map = products.set_index("SKU")["Product"].to_dict()

        for i, rec in enumerate(pending_recs):
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 2])
                with col1:
                    sku = rec["sku"]
                    prod_name = prod_map.get(sku, sku)
                    with st.container(border=True):
                        st.markdown(f"**{sku}**")
                        st.caption(prod_name)
                        st.caption(f"{rec['source_warehouse']} → {rec['destination_warehouse']}")
                with col2:
                    st.metric("Quantity", f"{rec['transfer_quantity']:,} units")
                    st.caption(f"Lead time: {rec['lead_time_days']} day(s)")
                with col3:
                    st.metric("Cost", f"{rec['transfer_cost_aed']:,.0f} AED")
                    st.caption(f"Shortage reduction: {rec['expected_unmet_avoided']:.0f}")
                with col4:
                    st.metric("Net Benefit", f"{rec['estimated_net_benefit_aed']:,.0f} AED")
                    st.markdown(f"**Status: {rec['approval_status']}**")
                with col5:
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("✓ Approve", key=f"approve_{rec['recommendation_id']}", type="primary"):
                            result = orchestrator.approve_transfer(rec["recommendation_id"], decided_by="dashboard_user")
                            if result.get("success"):
                                st.success(f"Approved: {rec['recommendation_id']}")
                            else:
                                st.error(result.get("message", "Approval failed"))
                            st.rerun()
                    with btn_col2:
                        if st.button("✕ Reject", key=f"reject_{rec['recommendation_id']}"):
                            result = orchestrator.reject_transfer(rec["recommendation_id"], decided_by="dashboard_user")
                            if result.get("success"):
                                st.success(f"Rejected: {rec['recommendation_id']}")
                            else:
                                st.error(result.get("message", "Rejection failed"))
                            st.rerun()

    # ── Approval History ──
    section_header("Approval History — All Decisions")
    history_df = pd.DataFrame(all_recs)

    if not history_df.empty:
        display_cols = ["recommendation_id", "sku", "source_warehouse", "destination_warehouse",
                        "transfer_quantity", "approval_status", "decision_timestamp", "decided_by"]
        available_cols = [c for c in display_cols if c in history_df.columns]
        display_history = history_df[available_cols].copy()

        col_names = {
            "recommendation_id": "Recommendation ID",
            "sku": "SKU",
            "source_warehouse": "Source",
            "destination_warehouse": "Destination",
            "transfer_quantity": "Quantity",
            "approval_status": "Status",
            "decision_timestamp": "Decision Time",
            "decided_by": "Decided By",
        }
        display_history = display_history.rename(columns=col_names)

        if "Decision Time" in display_history.columns:
            display_history["Decision Time"] = display_history["Decision Time"].apply(
                lambda x: str(x)[:19] if x and str(x) != "None" else "—"
            )

        st.dataframe(display_history, use_container_width=True, hide_index=True, height=300)

    # ── Audit Trail ──
    section_header("Audit Trail")
    audit = orchestrator.get_audit_trail(limit=30)
    if audit:
        audit_df = pd.DataFrame(audit)
        display_audit = audit_df[["timestamp", "agent_name", "action", "details"]].copy()
        display_audit["timestamp"] = display_audit["timestamp"].apply(lambda x: str(x)[:19] if x else "")
        display_audit = display_audit.rename(columns={
            "timestamp": "Timestamp", "agent_name": "Agent",
            "action": "Action", "details": "Details",
        })
        st.dataframe(display_audit, use_container_width=True, hide_index=True, height=250)
    else:
        st.info("No audit entries yet.")

    # ── Regenerate Recommendations ──
    section_header("Regenerate Recommendations")
    st.warning("""
    Regenerating recommendations will clear existing recommendations for this scenario
    and re-run the optimization. Audit history is preserved.
    """)
    if st.button("🔄 Regenerate Recommendations", key="regen_recs"):
        with st.spinner("Re-running optimization..."):
            try:
                opt_result = orchestrator.get_transfer_recommendations(scenario, force_reload=True)
                st.success(f"Regenerated! {opt_result.get('num_recommendations', 0)} recommendations loaded.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
