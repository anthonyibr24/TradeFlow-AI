"""Page 5 — Agentic AI Control Center."""

import streamlit as st
import pandas as pd
import json
from datetime import datetime
from components.styling import (
    inject_css, kpi_card, section_header, page_title, agent_card,
    BLUE, GREEN, ORANGE, TEAL, RED, GRAY,
)
from components.styling import RISK_COLORS


AGENT_INFO = [
    {"name": "Forecasting Agent", "desc": "Loads XGBoost demand forecasts, retrieves per-SKU predictions",
     "color": BLUE, "task": "get_demand_forecast"},
    {"name": "Inventory Risk Agent", "desc": "Analyzes shortages, excess stock, ageing risks",
     "color": ORANGE, "task": "analyze_inventory"},
    {"name": "Optimization Agent", "desc": "Runs scipy.optimize.milp transfer optimization",
     "color": TEAL, "task": "get_transfer_recommendations"},
    {"name": "Explanation Agent", "desc": "Generates deterministic explanations from actual results",
     "color": "#7C3AED", "task": "explain_transfer"},
    {"name": "Approval Agent", "desc": "Manages human approval workflow with SQLite persistence",
     "color": GREEN, "task": "approve_transfer"},
    {"name": "Orchestrator Agent", "desc": "Coordinates all agents, supports individual calls",
     "color": BLUE, "task": "run_full_workflow"},
]


def render(data: dict, scenario: str, orchestrator=None):
    """Render the agentic AI control center page."""
    inject_css()
    # Store data in session state for helper functions to access product names
    st.session_state["_shared_data"] = data
    page_title("Agentic AI Control Center",
               "Six specialized agents coordinating supply chain intelligence")

    # ── Agent Status Cards ──
    section_header("Agent Status")
    cols = st.columns(3)
    for i, agent in enumerate(AGENT_INFO):
        with cols[i % 3]:
            # Get latest activity from agent log
            activity = ""
            if orchestrator:
                log = orchestrator.get_agent_log(limit=100)
                agent_logs = [l for l in log if l.get("agent_name") == agent["name"].replace(" ", "")]
                if agent_logs:
                    latest = agent_logs[0]
                    activity = f"Last: {latest.get('task', 'N/A')} at {latest.get('timestamp', '')[:19]}"
            agent_card(agent["name"], agent["desc"], status="Ready",
                       accent=agent["color"], activity=activity)

    # ── Run AI Analysis ──
    section_header("Run Supply Chain AI Analysis")
    st.markdown("Execute the full agent workflow: Forecasting → Inventory Analysis → Optimization → Explanation → Approval")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🚀 Run Full Workflow", type="primary", use_container_width=True):
            if orchestrator:
                with st.spinner("Running agent workflow..."):
                    try:
                        result = orchestrator.run_full_workflow(scenario)
                        st.session_state["workflow_result"] = result
                        st.session_state["workflow_status"] = "success"
                        st.success(f"Workflow completed! {result.get('optimization', {}).get('num_recommendations', 0)} recommendations generated.")
                    except Exception as e:
                        st.session_state["workflow_status"] = "error"
                        st.error(f"Workflow error: {e}")
            else:
                st.error("Orchestrator not initialized.")
    with col2:
        if "workflow_status" in st.session_state:
            if st.session_state["workflow_status"] == "success":
                result = st.session_state.get("workflow_result", {})
                opt = result.get("optimization", {})
                col_a, col_b, col_c, col_d = st.columns(4)
                with col_a:
                    kpi_card("Recommendations", f"{opt.get('num_recommendations', 0)}", "transfers", accent=BLUE)
                with col_b:
                    kpi_card("Unmet Avoided", f"{opt.get('unmet_avoided', 0):.0f}", "units", accent=GREEN)
                with col_c:
                    kpi_card("Net Benefit", f"{opt.get('net_economic_benefit', 0):,.0f}", "AED", accent=TEAL)
                with col_d:
                    kpi_card("Reduction", f"{opt.get('unmet_reduction_pct', 0):.1f}%", "of unmet demand", accent=GREEN)

    # ── Workflow Visualization ──
    section_header("Workflow Sequence")
    steps = [
        ("1. Forecasting", "Forecast Agent retrieves XGBoost predictions", BLUE),
        ("2. Inventory Analysis", "Inventory Risk Agent identifies shortages/excess", ORANGE),
        ("3. Optimization", "Optimization Agent runs MILP solver", TEAL),
        ("4. Explanation", "Explanation Agent generates business-friendly text", "#7C3AED"),
        ("5. Human Approval", "Approval Agent presents recommendations for review", GREEN),
    ]
    cols = st.columns(5)
    for i, (title, desc, color) in enumerate(steps):
        with cols[i]:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(desc)
                st.markdown(f"🟢 Complete")
            if i < 4:
                st.markdown("**→**")

    # ══════════════════════════════════════════════════════════════
    # P1: Live What-If Scenario Simulator
    # ══════════════════════════════════════════════════════════════
    section_header("Live What-If Scenario Simulator")
    st.caption("Interactive simulation — no physical inventory changes. "
               "Modifies a working copy of inventory and reruns risk + MILP optimization.")

    with st.expander("How the simulator works", expanded=False):
        st.markdown("""
        **What this tool does:** Modifies one SKU-warehouse combination at a time on a temporary copy
        of your inventory, then reruns the full risk analysis and MILP optimization to show how the
        results would change.

        **Each simulation is independent.** When you click **Apply & Recalculate**, only the currently
        selected values are applied. Previous modifications are discarded.

        **Reset Scenario** clears the current simulation and returns to the baseline view.

        **Technical definitions** of each metric are available in the Metric Definitions section below.
        """)

    st.session_state.setdefault("data_dir", None)
    # Resolve data_dir from app context
    import os as _os
    _data_dir = st.session_state.get("data_dir") or _os.environ.get("TRADEFLOW_DATA_DIR")
    if not _data_dir:
        # Fallback: discover from app directory structure
        _app_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        for _cand in [
            _os.path.join(_app_dir, "data"),
            _os.path.join(_os.path.dirname(_app_dir), "Datasets"),
        ]:
            if _os.path.exists(_cand) and _os.path.exists(_os.path.join(_cand, "products.csv")):
                _data_dir = _cand
                break

    if not _data_dir or not _os.path.exists(_data_dir):
        st.warning("Data directory not found. What-If simulator unavailable.")
    else:
        from components.metrics import get_scenario_inventory
        inv_df = get_scenario_inventory(data, scenario)
        products_df = data["products"]

        col_sim1, col_sim2, col_sim3, col_sim4 = st.columns(4)
        with col_sim1:
            sim_sku = st.selectbox("SKU", sorted(inv_df["SKU"].unique().tolist()),
                                   key="whatif_sku", help="Select a SKU to modify")
        with col_sim2:
            sim_wh = st.selectbox("Warehouse", sorted(inv_df["Warehouse"].unique().tolist()),
                                  key="whatif_wh", help="Select a warehouse")
        with col_sim3:
            combo_row = inv_df[(inv_df["SKU"] == sim_sku) & (inv_df["Warehouse"] == sim_wh)]
            current_avail = int(combo_row["Available_Stock"].values[0]) if not combo_row.empty else 0
            sim_new_avail = st.number_input("Available Inventory", min_value=0, max_value=10000,
                                            value=current_avail, step=1, key="whatif_avail")
        with col_sim4:
            current_safety = int(combo_row["Safety_Stock"].values[0]) if not combo_row.empty else 0
            sim_new_safety = st.number_input("Safety Stock (optional)", min_value=0, max_value=500,
                                             value=current_safety, step=1, key="whatif_safety")

        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 3])
        with col_btn1:
            run_whatif = st.button("Apply & Recalculate", type="primary",
                                   key="btn_whatif", use_container_width=True)
        with col_btn2:
            reset_whatif = st.button("Reset Scenario", key="btn_reset_whatif",
                                     use_container_width=True)

        if reset_whatif:
            st.session_state.pop("whatif_result", None)
            st.rerun()

        if run_whatif:
            with st.spinner("Running what-if simulation (risk + MILP optimization)..."):
                try:
                    from simulation_engine import run_whatif_simulation
                    whatif_result = run_whatif_simulation(
                        _data_dir, scenario, sim_sku, sim_wh,
                        int(sim_new_avail), int(sim_new_safety),
                    )
                    st.session_state["whatif_result"] = whatif_result
                except Exception as e:
                    st.error(f"Simulation error: {e}")

        if "whatif_result" in st.session_state:
            wf = st.session_state["whatif_result"]
            if "error" in wf:
                st.error(f"Simulation error: {wf['error']}")
            else:
                cc = wf["changed_combo"]
                br = wf["baseline_risk"]
                bo = wf["baseline_opt"]
                mr = wf["modified_risk"]
                mo = wf["modified_opt"]

                _render_whatif_visual(cc, br, bo, mr, mo, wf)

                st.caption(wf["forecast_note"])

    # ══════════════════════════════════════════════════════════════
    # P2: Supply-Chain Disruption Simulator
    # ══════════════════════════════════════════════════════════════
    section_header("Supply-Chain Disruption Simulator")
    st.caption("Uses actual disruptions.csv records. Applies delays to inbound orders or transfer routes.")

    disruptions_df = data.get("disruptions")
    if disruptions_df is None or disruptions_df.empty:
        st.warning("disruptions.csv not found or empty.")
    else:
        disruption_options = ["No Disruption", "Component Supply Shortage", "Shipping Route Delay"]
        selected_disruption = st.selectbox("Select Disruption Scenario", disruption_options,
                                           key="disruption_select")

        if st.button("Run Disruption Simulation", type="primary", key="btn_disruption"):
            with st.spinner("Running disruption simulation..."):
                try:
                    from simulation_engine import run_disruption_simulation
                    disr_result = run_disruption_simulation(_data_dir, scenario, selected_disruption)
                    st.session_state["disruption_result"] = disr_result
                except Exception as e:
                    st.error(f"Disruption simulation error: {e}")

        if "disruption_result" in st.session_state:
            dr = st.session_state["disruption_result"]
            if "error" in dr:
                st.error(f"Disruption error: {dr['error']}")
            else:
                dbr = dr["baseline_risk"]
                dbo = dr["baseline_opt"]
                dmr = dr["modified_risk"]
                dmo = dr["modified_opt"]

                d_delta_unmet = dmr["total_unmet"] - dbr["total_unmet"]
                d_delta_recs = dmo["num_recommendations"] - dbo["num_recommendations"]
                d_delta_benefit = dmo["net_economic_benefit"] - dbo["net_economic_benefit"]
                d_delta_post_unmet = dmo["post_transfer_unmet"] - dbo["post_transfer_unmet"]
                d_delta_baseline_unmet = dmo["baseline_unmet"] - dbo["baseline_unmet"]

                # ── A. Disruption Summary — colorful card ──
                section_header("Disruption Summary")
                affected_count = len(dr.get("affected_items", []))
                affected_orders = dr.get('affected_orders_count', 'N/A')

                with st.container(border=True):
                    st.markdown(f"#### {dr['disruption_type']}")
                    c_s1, c_s2, c_s3 = st.columns(3)
                    with c_s1:
                        st.metric("Delay Duration", f"{dr['delay_days']} days")
                    with c_s2:
                        st.metric("Affected Items", f"{affected_count}")
                    with c_s3:
                        st.metric("Affected Orders", f"{affected_orders}")
                    if dr.get('affected_detail'):
                        st.caption(dr['affected_detail'])

                # ── B. Impact on Supply Chain — 3 colorful KPI cards ──
                section_header("Impact on Supply Chain")

                _d_no_change = abs(d_delta_unmet) < 0.5 and abs(d_delta_benefit) < 1 and abs(d_delta_post_unmet) < 0.5

                # Determine colors
                shortage_color = RED if d_delta_post_unmet > 0.5 else (GREEN if d_delta_post_unmet < -0.5 else BLUE)
                transfer_color = ORANGE if abs(d_delta_recs) > 0 else BLUE
                benefit_color = RED if d_delta_benefit < -1 else (GREEN if d_delta_benefit > 1 else BLUE)

                col_d1, col_d2, col_d3 = st.columns(3)
                with col_d1:
                    shortage_icon = "▲" if d_delta_post_unmet > 0.5 else ("▼" if d_delta_post_unmet < -0.5 else "→")
                    kpi_card(
                        "Additional Projected Shortages",
                        f"{d_delta_post_unmet:,.1f}",
                        f"Baseline: {dbo['post_transfer_unmet']:,.1f} → Disrupted: {dmo['post_transfer_unmet']:,.1f}",
                        accent=shortage_color,
                    )
                with col_d2:
                    kpi_card(
                        "Change in Recommended Transfers",
                        f"{d_delta_recs:+d}",
                        f"Baseline: {dbo['num_recommendations']} → Disrupted: {dmo['num_recommendations']}",
                        accent=transfer_color,
                    )
                with col_d3:
                    kpi_card(
                        "Change in Net Economic Benefit",
                        f"{d_delta_benefit:+,.0f} AED",
                        f"Baseline: {dbo['net_economic_benefit']:,.0f} → Disrupted: {dmo['net_economic_benefit']:,.0f}",
                        accent=benefit_color,
                    )

                # Full comparison table in collapsed expander
                with st.expander("View Detailed Analysis", expanded=False):
                    _render_comparison_table(dbr, dbo, dmr, dmo)

                # ── C. Overall Impact — clear indicator ──
                section_header("Overall Impact")
                if _d_no_change:
                    with st.container(border=True):
                        st.markdown("### 🟢 Low Impact")
                        st.markdown("No measurable change detected. The affected SKUs or routes are not critical to the current scenario.")
                elif abs(d_delta_post_unmet) > 50 or abs(d_delta_benefit) > 5000:
                    with st.container(border=True):
                        st.markdown("### 🔴 High Impact")
                        st.markdown("Significant disruption detected. Projected shortages or economic impact changed substantially.")
                elif abs(d_delta_post_unmet) > 5 or abs(d_delta_benefit) > 500:
                    with st.container(border=True):
                        st.markdown("### 🟠 Moderate Impact")
                        st.markdown("Some changes detected. Review the impact cards above for details.")
                else:
                    with st.container(border=True):
                        st.markdown("### 🟢 Low Impact")
                        st.markdown("Minor changes detected. The disruption had limited effect on the current scenario.")

                # ── D. AI Recommendation — one short recommendation ──
                section_header("AI Recommendation")
                if _d_no_change:
                    st.info("No measurable impact was detected under current assumptions. "
                            "Monitor for secondary effects if the disruption persists.")
                elif d_delta_unmet > 0 or d_delta_post_unmet > 0:
                    st.warning("The disruption increases projected shortages. "
                               "Consider expediting alternative supply routes or adjusting safety stock.")
                elif d_delta_benefit < -1:
                    st.warning("The disruption reduces projected economic benefit. "
                               "Review affected transfer routes and consider alternative sourcing.")
                else:
                    st.info("No negative impact detected under the current scenario.")

                # ── E. Technical Details expander ──
                with st.expander("View Technical Details", expanded=False):
                    is_component = "Component" in dr.get("disruption_type", "")
                    is_route = "Route" in dr.get("disruption_type", "")
                    if is_component:
                        st.markdown(f"- Component shortage delays inbound POs by {dr['delay_days']} days.")
                        if abs(d_delta_baseline_unmet) < 0.5 and abs(d_delta_benefit) < 1:
                            st.markdown("- Affected SKUs may not be in shortage, or delayed orders still arrive within the 30-day window.")
                    elif is_route:
                        st.markdown(f"- Shipping route delay increases lead time by {dr['delay_days']} days.")
                        if abs(d_delta_recs) < 1 and abs(d_delta_benefit) < 1:
                            st.markdown("- The affected route may not be used by any recommended transfer, or the delay is small enough that the same shortages remain reducible.")

                # ── F. Disruption Verification ──
                vdata = dr.get("verification_data", {})
                if vdata:
                    with st.expander("Disruption Verification — Records Modified", expanded=False):
                        if vdata.get("type") == "component_shortage":
                            st.markdown(f"**Affected SKUs:** {', '.join(vdata['affected_skus'])}")
                            st.markdown(f"**Delay applied:** {vdata['delay_days']} days")
                            st.markdown(f"**Orders pushed outside 30-day horizon:** {vdata.get('orders_pushed_outside_horizon', 0)}")
                            orders = vdata.get("affected_orders", [])
                            if orders:
                                st.markdown("**Delayed Inbound Orders:**")
                                v_df = pd.DataFrame(orders)
                                v_df = v_df.rename(columns={
                                    "sku": "SKU", "warehouse": "Warehouse",
                                    "original_arrival": "Original Arrival",
                                    "disrupted_arrival": "Disrupted Arrival",
                                    "quantity": "Quantity",
                                })
                                st.dataframe(v_df, use_container_width=True, hide_index=True)
                        elif "route" in vdata:
                            st.markdown(f"**Route:** {vdata['route']}")
                            st.markdown(f"**Original lead time:** {vdata['original_lead_time']} days → **Disrupted:** {vdata['disrupted_lead_time']} days")
                            st.markdown(f"**Transfers using this route in baseline:** {vdata.get('transfers_using_route_in_baseline', 0)}")
                            td = vdata.get("transfer_details", [])
                            if td:
                                st.markdown("**Affected Transfers:**")
                                st.dataframe(pd.DataFrame(td), use_container_width=True, hide_index=True)
                            else:
                                st.markdown("No baseline transfers use this route.")

                st.caption(dr["forecast_note"])

    # ── Agent Activity Log ──
    section_header("Agent Activity Log")
    if orchestrator:
        log = orchestrator.get_agent_log(limit=50)
        if log:
            log_df = pd.DataFrame(log)
            log_df = log_df[["timestamp", "agent_name", "task", "status"]].copy()
            log_df["timestamp"] = log_df["timestamp"].apply(lambda x: x[:19] if x else "")
            log_df = log_df.rename(columns={
                "timestamp": "Timestamp", "agent_name": "Agent",
                "task": "Task", "status": "Status",
            })
            st.dataframe(log_df, use_container_width=True, hide_index=True, height=300)
        else:
            st.info("No agent activity logged yet. Run the workflow to generate logs.")
    else:
        # Show from CSV as fallback
        workflow_log = data.get("agent_workflow_log")
        if workflow_log is not None and not workflow_log.empty:
            log_df = workflow_log[["timestamp", "agent_name", "task", "status"]].head(50).copy()
            log_df["timestamp"] = log_df["timestamp"].apply(lambda x: str(x)[:19] if x else "")
            log_df = log_df.rename(columns={
                "timestamp": "Timestamp", "agent_name": "Agent",
                "task": "Task", "status": "Status",
            })
            st.dataframe(log_df, use_container_width=True, hide_index=True, height=300)
        else:
            st.info("No agent activity log available.")

    # ── Unmet Demand Explanation (P3) ──
    section_header("Metric Definitions & Assumptions")
    # Compute dynamic values for the current scenario
    try:
        from components.metrics import get_scenario_inventory, compute_risk_summary
        from tradeflow_agents.optimization_agent import OptimizationAgent
        _inv = get_scenario_inventory(data, scenario)
        _risk = compute_risk_summary(_inv, data["forecast_30d"])
        _static_unmet = _risk["total_unmet"]
        _opt_agent = OptimizationAgent(_data_dir)
        _opt = _opt_agent.get_transfer_recommendations(scenario)
        _dynamic_unmet = _opt.get("baseline_unmet", 0)
        _net_benefit = _opt.get("net_economic_benefit", 0)
        _n_recs = _opt.get("num_recommendations", 0)
    except Exception:
        _static_unmet = 0
        _dynamic_unmet = 0
        _net_benefit = 0
        _n_recs = 0

    st.info(f"""
    **Why do unmet-demand figures differ across pages?**

    | Metric | Value (Current Scenario) | Calculation | Where Shown |
    |---|---|---|---|
    | **Static unmet demand** | {_static_unmet:,.0f} units | `max(0, Forecast_30d − Available_Stock)` — a simple gap check ignoring inbound orders | Executive Dashboard |
    | **Dynamic unmet demand** | {_dynamic_unmet:,.1f} units | Daily simulation that accounts for inbound PO arrivals during the 30-day horizon | Transfer Optimization |
    | **Recommended transfers** | {_n_recs} | MILP optimizer selects cost-effective transfers to reduce shortages | Transfer Optimization |
    | **Projected net economic benefit** | {_net_benefit:,.0f} AED | Margin preserved from shortage reduction − transfer cost | Transfer Optimization |

    **Explanation:** The Executive Dashboard uses a **static risk snapshot** (forecast vs. current stock).
    The Transfer Optimization page uses the **daily inventory simulation** from the MILP optimizer, which
    credits inbound purchase orders that arrive within the horizon. This is why the simulation figure is
    lower — some shortages are covered by scheduled arrivals. Both are correct; they measure different things.

    **Economic benefit:** Projected Net Benefit = Projected Margin Preserved − Transfer Cost.
    All values are **simulated projections**, not realized savings. Realized outcomes remain zero
    until physical transfers are executed.
    """)

    # ── AI Assistant ──
    section_header("AI Supply Chain Assistant")
    st.caption("Ask questions about your supply chain. The assistant uses agent tools to retrieve factual answers — no LLM API key required.")

    # Initialize chat history
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Display chat history
    for msg in st.session_state["chat_messages"]:
        if msg["role"] == "user":
            with st.container(border=True):
                st.markdown(f"**You:** {msg['content']}")
        else:
            with st.container(border=True):
                st.markdown(f"**AI Assistant:**")
                st.markdown(msg["content"])

    # Suggested questions
    st.markdown("**Suggested questions:**")
    suggestions = [
        "Which warehouse has the highest shortage risk?",
        "What products should we transfer?",
        "How much money could the proposed transfers save?",
        "Which warehouse has the most ageing inventory?",
    ]
    cols = st.columns(4)
    for i, q in enumerate(suggestions):
        with cols[i]:
            if st.button(q, key=f"suggest_{i}", use_container_width=True):
                st.session_state["chat_messages"].append({"role": "user", "content": q})
                answer = _answer_question(q, data, scenario, orchestrator)
                st.session_state["chat_messages"].append({"role": "assistant", "content": answer})
                st.rerun()

    # Input box
    user_input = st.text_input("Ask a question:", key="chat_input",
                                placeholder="Type your supply chain question...",
                                label_visibility="collapsed")
    if st.button("Send", type="primary") and user_input:
        st.session_state["chat_messages"].append({"role": "user", "content": user_input})
        answer = _answer_question(user_input, data, scenario, orchestrator)
        st.session_state["chat_messages"].append({"role": "assistant", "content": answer})
        st.rerun()


def _answer_question(question: str, data: dict, scenario: str, orchestrator=None) -> str:
    """Deterministic tool-driven assistant that answers supply chain questions."""
    q = question.lower()
    inv_df = data["scenario_inventory"] if scenario == "demonstration" else data["inventory"]
    forecast_30d = data["forecast_30d"]
    products = data["products"]
    opt_summary_data = data.get("opt_summary")

    merged = inv_df.merge(forecast_30d[["SKU", "Warehouse", "Forecast_30d"]], on=["SKU", "Warehouse"])
    merged["Unmet_Demand"] = (merged["Forecast_30d"] - merged["Available_Stock"]).clip(lower=0)
    merged["Excess_Stock"] = (merged["Available_Stock"] - merged["Forecast_30d"] - merged["Safety_Stock"]).clip(lower=0)

    # Which warehouse has highest shortage risk?
    if "highest shortage" in q or "shortage risk" in q:
        wh_unmet = merged.groupby("Warehouse")["Unmet_Demand"].sum()
        if wh_unmet.max() > 0:
            wh = wh_unmet.idxmax()
            return f"**{wh}** has the highest projected unmet demand at **{wh_unmet[wh]:.0f} units** across all SKUs. This represents the greatest shortage risk in the {'demonstration' if scenario == 'demonstration' else 'original'} scenario."
        else:
            return "No warehouse has projected shortages in this scenario. All inventory levels are sufficient."

    # Financial / benefit questions — checked BEFORE transfer-list handler
    # Matches: "economic benefit", "how much money", "save", "projected benefit", "total benefit"
    elif ("benefit" in q or "money" in q or "save" in q or "how much" in q or
          "economic" in q or "cost" in q or "value" in q):
        if opt_summary_data is not None:
            net = opt_summary_data[opt_summary_data["Metric"] == "Net economic benefit"]["Value"].iloc[0]
            cost = opt_summary_data[opt_summary_data["Metric"] == "Total transfer cost"]["Value"].iloc[0]
            margin = opt_summary_data[opt_summary_data["Metric"] == "Estimated margin preserved"]["Value"].iloc[0]
            num = opt_summary_data[opt_summary_data["Metric"] == "Number of recommended transfers"]["Value"].iloc[0]
            recs_df = data.get("transfer_recs")
            individual_sum = recs_df["Estimated_Net_Benefit_AED"].sum() if recs_df is not None and not recs_df.empty else 0
            return (f"The proposed transfers project a **system-wide simulated net economic benefit of {net:,.0f} AED**.\n\n"
                    f"**Two different benefit metrics:**\n"
                    f"- **System-wide simulated net benefit**: **{net:,.0f} AED** — from the daily inventory simulation that accounts for lead times, inbound arrivals, and demand fulfillment dynamics.\n"
                    f"- **Sum of individual transfer benefits**: **{individual_sum:,.0f} AED** — simple arithmetic sum of each transfer's estimated net benefit, does not account for transfer interactions.\n\n"
                    f"**Breakdown of the system-wide benefit:**\n"
                    f"- Transfer cost: {cost:,.0f} AED\n"
                    f"- Margin preserved: {margin:,.0f} AED\n"
                    f"- {int(num)} transfers recommended\n\n"
                    f"All figures are projected estimates from simulation, not realized savings. "
                    f"Transfers require human approval before execution.")
        return "Optimization data not available for this scenario."

    # What products should we transfer? (list question — more specific to avoid catching benefit questions)
    elif "transfer" in q and ("what" in q or "which" in q or "should" in q or "list" in q):
        recs_df = data.get("transfer_recs")
        if recs_df is not None and not recs_df.empty:
            top5 = recs_df.nlargest(5, "Estimated_Net_Benefit_AED")
            lines = [f"Based on the MILP optimization, here are the top 5 recommended transfers:"]
            for _, r in top5.iterrows():
                lines.append(f"- **{r['SKU']}**: {r['Source_Warehouse']} → {r['Destination_Warehouse']}, {r['Transfer_Quantity']} units, net benefit {r['Estimated_Net_Benefit_AED']:.0f} AED")
            lines.append(f"\nTotal: {len(recs_df)} transfers, {recs_df['Transfer_Quantity'].sum()} units, projected net benefit {recs_df['Estimated_Net_Benefit_AED'].sum():,.0f} AED.")
            return "\n".join(lines)
        else:
            return "No transfer recommendations exist for this scenario. The original scenario has no shortages, so no transfers are needed."

    # Why is SKU-016 being transferred?
    elif "why" in q and ("sku" in q or "transfer" in q):
        recs_df = data.get("transfer_recs")
        if recs_df is None or recs_df.empty:
            return "No transfer recommendations exist for this scenario."

        # Try to find the SKU mentioned
        import re
        sku_match = re.search(r"sku[-\s]?(\d+)", q)
        if sku_match:
            sku_num = sku_match.group(1).zfill(3)
            sku = f"SKU-{sku_num}"
            rec = recs_df[recs_df["SKU"] == sku]
            if rec.empty:
                return f"No transfer recommendation found for {sku}."
            r = rec.iloc[0]
            prod = products[products["SKU"] == sku]
            prod_name = prod.iloc[0]["Product"] if not prod.empty else sku
            return (f"**{sku} ({prod_name})** is being transferred from **{r['Source_Warehouse']}** to "
                    f"**{r['Destination_Warehouse']}** because:\n"
                    f"- {r['Source_Warehouse']} has transferable surplus stock above its own forecast + safety stock\n"
                    f"- {r['Destination_Warehouse']} faces a projected shortage of {r['Expected_Unmet_Demand_Avoided']:.0f} units\n"
                    f"- Transferring {r['Transfer_Quantity']} units reduces this shortage at a cost of {r['Transfer_Cost_AED']:.2f} AED\n"
                    f"- Projected net benefit: **{r['Estimated_Net_Benefit_AED']:.2f} AED**")
        return "Please specify a SKU (e.g., 'Why is SKU-016 being transferred?')."

    # What happens if we reject a transfer?
    elif "reject" in q:
        return ("If a transfer recommendation is **rejected**, it will not be executed. "
                "The rejected transfer's projected benefit (unmet demand avoided + margin preserved) "
                "will **not be realized**. The approved-plan impact will be lower than the proposed "
                "optimization impact. You can see the updated impact in the Approval Center page.")

    # Which warehouse has most ageing inventory?
    elif "ageing" in q or "aging" in q:
        ageing = data.get("scenario_ageing") if scenario == "demonstration" else data.get("stock_ageing")
        if ageing is not None:
            # Normalise Age_Bucket labels: CSV has "61-90 days" but code expects "61-90"
            buckets = ageing["Age_Bucket"].str.replace(" days", "", regex=False)
            old = ageing[buckets.isin(["61-90", "90+"])]
            by_wh = old.groupby("Warehouse")["Quantity"].sum()
            if by_wh.max() > 0:
                wh = by_wh.idxmax()
                return f"**{wh}** has the most aged inventory (61+ days) at **{by_wh[wh]:.0f} units**. This represents the highest ageing risk."
            return "No significant aged inventory detected."
        return "Ageing data not available."

    # Coverage ratio
    elif "coverage" in q:
        total_avail = merged["Available_Stock"].sum()
        total_fc = merged["Forecast_30d"].sum()
        ratio = total_avail / total_fc if total_fc > 0 else 0
        return (f"The system-wide inventory coverage ratio is **{ratio:.2f}x** the 30-day forecast demand. "
                f"Total available: {total_avail:,} units. Total forecast: {total_fc:,.0f} units.")

    # How many agents?
    elif "agent" in q and ("how many" in q or "what" in q):
        return ("TradeFlow AI has **6 specialized agents**:\n"
                "1. Forecasting Agent — XGBoost demand predictions\n"
                "2. Inventory Risk Agent — shortage/excess analysis\n"
                "3. Optimization Agent — MILP transfer optimization\n"
                "4. Explanation Agent — deterministic business explanations\n"
                "5. Approval Agent — human approval workflow with SQLite\n"
                "6. Orchestrator Agent — coordinates all agents")

    else:
        return ("I can answer questions about:\n"
                "- Which warehouse has the highest shortage risk?\n"
                "- What products should we transfer?\n"
                "- Why is SKU-016 being transferred?\n"
                "- How much money could the proposed transfers save?\n"
                "- What happens if we reject a transfer?\n"
                "- Which warehouse has the most ageing inventory?\n"
                "\nPlease ask one of these or similar questions.")


def _sim_kpi(unmet, excess, exposure, num_recs, net_benefit, baseline_unmet, post_unmet):
    """Helper: render KPI cards for a simulation snapshot."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_card("Unmet Demand", f"{unmet:,.0f}", "units (static gap)", accent=ORANGE)
    with col2:
        kpi_card("Excess Stock", f"{excess:,.0f}", "units above forecast + safety", accent="#7C3AED")
    with col3:
        kpi_card("Economic Exposure", f"{exposure:,.0f} AED", "margin at risk", accent=RED)
    with col4:
        kpi_card("Transfer Recs", f"{num_recs}", "recommended transfers", accent=BLUE)

    col5, col6, col7 = st.columns(3)
    with col5:
        kpi_card("Sim Baseline Unmet", f"{baseline_unmet:,.1f}", "dynamic (30-day sim)", accent=RED)
    with col6:
        kpi_card("Sim Post-Transfer Unmet", f"{post_unmet:,.1f}", "after transfers", accent=ORANGE)
    with col7:
        kpi_card("Net Benefit", f"{net_benefit:,.0f} AED", "projected (simulated)", accent=GREEN)


def _render_comparison_table(br, bo, mr, mo, show_diff=True):
    """Render a clean comparison table using native Streamlit dataframe.

    br = baseline_risk, bo = baseline_opt
    mr = modified_risk, mo = modified_opt
    """
    # Business-friendly metric names
    rows = [
        ("Current Stock Shortage (30-Day Forecast Gap)", br['total_unmet'], mr['total_unmet'], "lower_better"),
        ("Predicted Shortage After Incoming Deliveries", bo['baseline_unmet'], mo['baseline_unmet'], "lower_better"),
        ("Excess Stock (units above forecast + safety)", br['total_excess'], mr['total_excess'], "lower_better"),
        ("Estimated Value of Unfulfilled Demand (AED)", br['economic_exposure'], mr['economic_exposure'], "lower_better"),
        ("Recommended Transfers", bo['num_recommendations'], mo['num_recommendations'], "neutral"),
        ("Remaining Shortage After Transfers", bo['post_transfer_unmet'], mo['post_transfer_unmet'], "lower_better"),
        ("Estimated Net Economic Benefit (AED)", bo['net_economic_benefit'], mo['net_economic_benefit'], "higher_better"),
    ]

    def _fmt(val, name):
        if "Transfer" in name:
            return f"{int(val)}"
        elif "AED" in name:
            return f"{val:,.0f}"
        elif isinstance(val, (int, float)):
            return f"{val:,.1f}"
        return str(val)

    if show_diff:
        data = []
        for name, b_val, m_val, direction in rows:
            diff = m_val - b_val
            if abs(diff) < 0.05:
                change = "No change"
            else:
                sign = "+" if diff > 0 else ""
                if "Transfer" in name:
                    change = f"{sign}{int(diff)}"
                elif "AED" in name:
                    change = f"{sign}{diff:,.0f}"
                else:
                    change = f"{sign}{diff:,.1f}"

            # Emoji indicator
            if abs(diff) < 0.05:
                indicator = "—"
            elif direction == "lower_better":
                indicator = "✅" if diff < 0 else "🔴"
            elif direction == "higher_better":
                indicator = "✅" if diff > 0 else "🔴"
            else:
                indicator = "🔵"

            data.append({
                "Metric": name,
                "Before": _fmt(b_val, name),
                "After": _fmt(m_val, name),
                "Change": f"{indicator} {change}",
            })
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={
            "Metric": st.column_config.TextColumn(width="large"),
            "Before": st.column_config.TextColumn(width="small"),
            "After": st.column_config.TextColumn(width="small"),
            "Change": st.column_config.TextColumn(width="small"),
        })
    else:
        data = []
        for name, b_val, m_val, _ in rows:
            data.append({
                "Metric": name,
                "Baseline": _fmt(b_val, name),
                "Modified": _fmt(m_val, name),
            })
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)


def _format_transfer_row(rec, change_type="", cc=None):
    """Format a transfer recommendation dict for display."""
    sku = rec.get("sku", "")
    src = rec.get("source_warehouse", "")
    dst = rec.get("destination_warehouse", "")
    qty = rec.get("transfer_quantity", 0)
    cost = rec.get("transfer_cost_aed", 0)
    unmet_avoided = rec.get("expected_unmet_avoided", 0)
    net_benefit = rec.get("estimated_net_benefit_aed", 0)
    product_name = rec.get("product_name", sku)
    lead_time = rec.get("lead_time_days", 0)

    highlight = ""
    if cc:
        if sku == cc.get("sku") or src == cc.get("warehouse") or dst == cc.get("warehouse"):
            highlight = " *"

    return {
        "Product": f"{product_name} ({sku}){highlight}",
        "From → To": f"{src} → {dst}",
        "Qty": int(qty),
        "Transfer Cost (AED)": f"{cost:,.0f}",
        "Shortage Reduction (units)": f"{unmet_avoided:,.0f}",
        "Net Benefit (AED)": f"{net_benefit:,.0f}",
        "Lead Time (days)": lead_time,
        "Change": change_type,
    }


def _render_transfer_card_native(rec, change_label=""):
    """Render a single transfer recommendation as a native Streamlit bordered container."""
    sku = rec.get("sku", "")
    src = rec.get("source_warehouse", "")
    dst = rec.get("destination_warehouse", "")
    qty = rec.get("transfer_quantity", 0)
    cost = rec.get("transfer_cost_aed", 0)
    unmet_avoided = rec.get("expected_unmet_avoided", 0)
    net_benefit = rec.get("estimated_net_benefit_aed", 0)
    product_name = rec.get("product_name", sku)
    lead_time = rec.get("lead_time_days", 0)

    with st.container(border=True):
        if change_label:
            st.markdown(f"**{change_label} Transfer**")
        st.markdown(f"#### {product_name} ({sku})")
        st.markdown(f"**{src} → {dst}**")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Quantity", f"{int(qty):,}", "units")
        with c2:
            st.metric("Transfer Cost", f"{cost:,.0f}", "AED")
        with c3:
            st.metric("Shortage Reduction", f"{unmet_avoided:,.0f}", "units")
        with c4:
            st.metric("Estimated Benefit", f"{net_benefit:,.0f}", "AED")
        st.caption(f"Delivery time: {lead_time} days")


def _render_whatif_visual(cc, br, bo, mr, mo, wf):
    """What-If Simulator result rendering — simplified with colorful KPI cards."""
    td = wf.get("transfer_diff")
    no_transfer_explanation = wf.get("no_transfer_explanation")

    delta_unmet = mr['total_unmet'] - br['total_unmet']
    delta_recs = mo['num_recommendations'] - bo['num_recommendations']
    delta_benefit = mo['net_economic_benefit'] - bo['net_economic_benefit']
    delta_post_unmet = mo['post_transfer_unmet'] - bo['post_transfer_unmet']

    ops_worsened = delta_unmet > 0.5 or delta_post_unmet > 0.5
    fin_improved = delta_benefit > 1
    no_result_change = all(abs(d) < 0.5 for d in [delta_unmet, delta_recs, delta_benefit, delta_post_unmet])

    # Detect whether inputs actually changed
    inv_changed = cc['old_available'] != cc['new_available']
    safety_changed = cc.get('old_safety', 0) != cc.get('new_safety', 0)
    no_input_change = not inv_changed and not safety_changed

    # ── A. What Changed ──
    section_header("What You Changed")

    product_name = cc.get("sku", "")
    try:
        _data = st.session_state.get("_shared_data", {})
        if _data and "products" in _data:
            prod = _data["products"][_data["products"]["SKU"] == cc["sku"]]
            if not prod.empty:
                product_name = prod.iloc[0]["Product"]
    except Exception:
        pass

    # Show both inventory and safety-stock changes
    with st.container(border=True):
        st.markdown(f"#### {product_name} ({cc['sku']}) — {cc['warehouse']}")
        st.markdown(f"**Inventory:** {cc['old_available']:,} → {cc['new_available']:,} units")
        st.markdown(f"**Safety Stock:** {cc.get('old_safety', 0):,} → {cc.get('new_safety', 0):,} units")

    # Safety-stock deficit display
    if safety_changed and cc.get('new_safety', 0) > cc['new_available']:
        deficit = cc['new_safety'] - cc['new_available']
        st.warning(
            f"**Safety-Stock Status:** Available inventory ({cc['new_available']:,} units) is below "
            f"the required safety stock ({cc['new_safety']:,} units). "
            f"Current safety-stock deficit: **{deficit:,} units**. "
            f"This is a buffer deficit, separate from unmet customer demand."
        )

    # Early exit if no inputs changed
    if no_input_change:
        section_header("AI Explanation")
        st.info("**No Changes Detected**\n\n"
                "Modify available inventory or safety stock to explore how supply chain "
                "recommendations change.")
        return

    # ── B. Impact Summary — 3 colorful KPI cards ──
    section_header("Impact Summary")

    # Determine card colors
    shortage_color = GREEN if delta_post_unmet < -0.5 else (RED if delta_post_unmet > 0.5 else GRAY)
    transfer_color = GRAY if delta_recs == 0 else BLUE
    benefit_color = GREEN if delta_benefit > 1 else (RED if delta_benefit < -1 else GRAY)

    col_k1, col_k2, col_k3 = st.columns(3)
    with col_k1:
        kpi_card(
            "Remaining Shortages",
            f"{delta_post_unmet:+,.1f}",
            f"Baseline: {bo['post_transfer_unmet']:,.1f} → Modified: {mo['post_transfer_unmet']:,.1f}",
            accent=shortage_color,
        )
    with col_k2:
        kpi_card(
            "Recommended Transfers",
            f"{delta_recs:+d}",
            f"Baseline: {bo['num_recommendations']} → Modified: {mo['num_recommendations']}",
            accent=transfer_color,
        )
    with col_k3:
        kpi_card(
            "Projected Net Economic Benefit",
            f"{delta_benefit:+,.0f} AED",
            f"Baseline: {bo['net_economic_benefit']:,.0f} → Modified: {mo['net_economic_benefit']:,.0f}",
            accent=benefit_color,
        )

    # Full comparison table in collapsed expander
    with st.expander("View Detailed Analysis", expanded=False):
        _render_comparison_table(br, bo, mr, mo)

    # Warning if benefit increased but shortages also increased
    if ops_worsened and fin_improved:
        st.warning("**Mixed outcome:** Net benefit increased, but shortages also increased. "
                   "The optimizer found new transfer opportunities, but they don't fully cover the new shortage.")

    # ── C. Top Transfer Recommendation (native Streamlit) ──
    section_header("AI Transfer Recommendation")
    st.warning("These are **simulated recommendations only** — not saved to the Approval Center. "
               "Human approval is required before execution.")

    if td is not None:
        added = td.get("added", [])
        removed = td.get("removed", [])
        changed = td.get("changed", [])
        unchanged = td.get("unchanged", [])

        # Determine most relevant transfer to highlight
        top_rec = None
        top_change_label = ""
        if added:
            top_rec = added[0]
            top_change_label = "NEW"
        elif changed:
            top_rec = changed[0].get("modified", {})
            b_qty = changed[0]["baseline"].get("transfer_quantity", 0)
            m_qty = changed[0]["modified"].get("transfer_quantity", 0)
            top_change_label = f"CHANGED ({b_qty} → {m_qty})"

        if top_rec:
            _render_transfer_card_native(top_rec, top_change_label)

        # All other transfers in collapsed expander
        with st.expander("All Transfer Changes", expanded=False):
            if added:
                st.markdown(f"**New Transfers ({len(added)}):**")
                rows = [_format_transfer_row(r, "NEW", cc) for r in added]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if removed:
                st.markdown(f"**Removed Transfers ({len(removed)}):**")
                rows = [_format_transfer_row(r, "REMOVED", cc) for r in removed]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if changed:
                st.markdown(f"**Changed Quantity ({len(changed)}):**")
                rows = []
                for item in changed:
                    b = item["baseline"]
                    m = item["modified"]
                    b_qty = b.get("transfer_quantity", 0)
                    m_qty = m.get("transfer_quantity", 0)
                    diff = m_qty - b_qty
                    sign = "+" if diff > 0 else ""
                    row = _format_transfer_row(m, f"{b_qty} → {m_qty} ({sign}{diff})", cc)
                    rows.append(row)
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if unchanged:
                st.markdown(f"**Unchanged Transfers ({len(unchanged)}):**")
                rows = [_format_transfer_row(r, "Unchanged", cc) for r in unchanged]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # No-transfer explanation
        if no_transfer_explanation and no_transfer_explanation.get("has_shortage"):
            with st.expander("Why No Transfer for the Modified Warehouse?", expanded=False):
                reasons = no_transfer_explanation.get("reasons", [])
                for reason in reasons:
                    st.markdown(f"- {reason}")

                details = no_transfer_explanation.get("details", {})
                candidate_routes = details.get("candidate_routes", [])
                if candidate_routes:
                    with st.expander("Candidate Route Details (optimizer constraints)", expanded=False):
                        route_rows = []
                        for cr in candidate_routes:
                            route_rows.append({
                                "Source → Dest": f"{cr['source']} → {cr['destination']}",
                                "Cost/Unit (AED)": f"{cr['cost_per_unit_aed']:.2f}",
                                "Margin (AED)": f"{details.get('profit_margin_aed', 0):.2f}",
                                "Net Benefit/Unit": f"{cr['net_benefit_per_unit_aed']:.2f}",
                                "Transferable Stock": cr["transferable_stock"],
                                "Reducible Unmet": f"{cr['reducible_unmet_demand']:.0f}",
                                "Lead Time (days)": cr["lead_time_days"],
                            })
                        st.dataframe(pd.DataFrame(route_rows), use_container_width=True, hide_index=True)

        if not added and not removed and not changed:
            st.info("No transfer recommendations changed. The modification did not affect the optimizer's transfer plan.")

    # ── D. AI Explanation — simplified ──
    section_header("AI Explanation")

    # What Happened
    st.markdown("**What Happened?**")
    if no_result_change:
        if safety_changed and cc.get('new_safety', 0) > cc['new_available']:
            st.info(
                f"No Change in Transfer Recommendations. "
                f"The modified inputs were applied, but the optimizer selected the same transfer plan. "
                f"The safety-stock increase does not affect the optimizer's transfer logic because "
                f"the MILP objective minimizes unmet customer demand, not safety-stock deficits. "
                f"The optimizer already addresses shortages via transfers; raising safety stock "
                f"does not create new customer demand to fulfill."
            )
        else:
            st.info(
                "No Change in Transfer Recommendations. "
                "The modified inputs were applied, but the optimizer selected the same transfer plan."
            )
    elif ops_worsened and fin_improved:
        st.warning(f"Shortages increased by {abs(delta_post_unmet):,.0f} units, but the optimizer "
                   f"found new transfer opportunities generating {abs(delta_benefit):,.0f} AED in additional benefit.")
    elif delta_post_unmet < -0.5:
        st.success(f"Shortages decreased by {abs(delta_post_unmet):,.0f} units.")
    elif delta_recs > 0:
        st.info(f"The optimizer recommends {delta_recs} additional transfer(s) to address the change.")
    else:
        st.info(f"The modification changed the transfer plan without significantly affecting shortages.")

    # Recommended Action
    st.markdown("**Recommended Action**")
    if no_result_change:
        if safety_changed and cc.get('new_safety', 0) > cc['new_available']:
            st.info(
                "The safety-stock deficit does not automatically trigger a transfer. "
                "The optimizer only transfers stock to reduce projected unmet customer demand. "
                "Consider manually reviewing whether to increase inventory at this warehouse "
                "via purchase orders rather than transfers."
            )
        else:
            st.info("No action needed — the modification did not change the optimizer's recommendations.")
    elif ops_worsened and fin_improved:
        st.warning("Consider reverting unless the financial trade-off is acceptable.")
    elif delta_post_unmet < -0.5:
        st.success("Consider applying this adjustment to the actual inventory plan.")
    elif delta_recs > 0:
        st.info(f"Review the {delta_recs} new transfer recommendation(s) above and consider approving them.")
    else:
        st.info("Review the transfer changes above before deciding.")

    # Technical details in expander
    with st.expander("Technical Explanation", expanded=False):
        st.markdown("**Why?**")
        if cc['new_available'] < cc['old_available']:
            st.caption(f"Removing {cc['old_available'] - cc['new_available']:,} units from {cc['warehouse']} "
                       f"widened its shortage gap, requiring more stock to cover forecast demand.")
        elif cc['new_available'] > cc['old_available']:
            st.caption(f"Adding {cc['new_available'] - cc['old_available']:,} units to {cc['warehouse']} "
                       f"reduced its shortage gap, covering demand that previously required transfers.")
        elif no_result_change:
            st.caption("The modified SKU-warehouse combination is not involved in any shortage or transfer recommendation.")
        else:
            st.caption("The optimizer recalculated all transfer recommendations based on the modified inventory levels.")
