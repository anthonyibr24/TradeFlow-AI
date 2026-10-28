# TradeFlow AI — 5-Minute Demo Script

## 0:00–0:30 — Problem

> "Three warehouses — Dubai, Abu Dhabi, Sharjah — stock 20 SKUs. Demand is unevenly distributed.
> Some locations face shortages and lost sales. Others hold excess stock tying up capital.
> TradeFlow AI solves this with agentic AI: forecast, detect, optimize, explain, and require human approval."

**Action:** Show the Executive Dashboard sidebar. Select the **Demonstration** scenario.

## 0:30–1:15 — Demand Forecasting

> "The ForecastingAgent uses XGBoost to predict 30-day demand for every SKU-warehouse combination."

**Action:** Navigate to **Demand Forecasting** page.
- Point to the forecast table (60 rows: 20 SKUs × 3 warehouses).
- Show accuracy metrics (MAPE, MAE).
- Select a high-demand SKU to show the daily forecast chart.

## 1:15–2:00 — Inventory Intelligence

> "The InventoryRiskAgent classifies every combo as Critical, Warning, Excess, or Healthy."

**Action:** Navigate to **Inventory Intelligence** page.
- Show the risk table — point out Critical (shortage) combos.
- Scroll to **Inventory Ageing Analysis** — the chart now renders correctly (fixed label normalisation).
- Show the 30-day projection for a shortage SKU.

## 2:00–3:00 — Transfer Optimization

> "The OptimizationAgent runs a MILP solver. It found 28 transfers that reduce unmet demand by 98.9%."

**Action:** Navigate to **Transfer Optimization** page.
- Show KPIs: 28 transfers, 1,108 units, 2,021.50 AED cost, 44,817.17 AED net benefit.
- Show the transfer network graph.
- Select a transfer and read the AI explanation.
- Note: "All figures are projected estimates from simulation, not realized savings."

## 3:00–4:00 — Agentic AI and What-If Simulation

> "The Agent Control Center shows all six agents working together. Now let's do a live what-if."

**Action:** Navigate to **Agent Control Center** page.
- Show the agent workflow visualization (5 steps).
- Scroll to **Live What-If Scenario Simulator**.
- Select **SKU-003**, **Dubai**.
- Change Available Inventory from 43 → 209 (adding enough to cover the shortage).
- Click **Apply & Recalculate**.
- Show the Before vs After comparison:
  - Unmet demand drops by ~117 units
  - Recommendations drop from 28 → 27 (one transfer no longer needed)
  - Net benefit changes
- Note: "Interactive simulation — no physical inventory changes."

**Optional:** Scroll to **Supply-Chain Disruption Simulator**, select **Component Supply Shortage**, click **Run**. Show the affected SKUs and any impact. Note: "If the impact is minimal, it means the affected SKUs weren't in shortage — this is an honest result."

## 4:00–4:40 — Demand Uncertainty Analysis

> "AI forecasts are not guaranteed. Let's see what happens if demand is higher or lower than predicted."

**Action:** Navigate to **Demand Uncertainty** page.
- Show the uncertainty method explanation (875 test residuals, sigma_daily = 2.0, sigma_30d = 10.96).
- Show the comparison table: Low (22 transfers, 34,886 AED) vs Expected (28 transfers, 44,817 AED) vs High (30 transfers, 57,643 AED).
- Point out: "The optimizer produces **different recommendations** for each scenario — more transfers needed when demand is higher."
- Show the robust decision analysis: "If the expected plan is applied to high demand, unmet demand would be higher."
- Note: "These are empirical sensitivity bounds, not calibrated prediction intervals."

## 4:40–5:00 — Human Approval and Conclusion

> "No transfer is executed without human approval. The ApprovalAgent stores decisions in SQLite."

**Action:** Navigate to **Approval Center** page.
- Show pending recommendations.
- Approve one transfer.
- Reject another.
- Show the audit trail.
- Note: "Approvals persist across page refreshes. Duplicate decisions are prevented."

> "TradeFlow AI projects a net economic benefit of 44,817 AED from 28 inter-warehouse transfers.
> The system uses real XGBoost forecasts, real MILP optimization, and real inventory data.
> Demand uncertainty analysis shows the plan changes when demand is higher or lower than expected.
> All benefits are simulated projections — nothing is executed without human approval."

**Done.**
