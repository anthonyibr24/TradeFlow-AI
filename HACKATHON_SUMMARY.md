# TradeFlow AI — Hackathon Summary

## 1. Business Problem

Three warehouses (Dubai, Abu Dhabi, Sharjah) stock 20 SKUs with uneven distribution. Some locations face shortages (lost sales), others hold excess stock (tied-up capital), and ageing inventory ties up further value. Manual rebalancing is slow and lacks economic justification.

## 2. Datasets

| Dataset | Rows | Description |
|---|---|---|
| `products.csv` | 20 | SKU names, profit margins (AED/unit) |
| `scenario_inventory.csv` | 60 | Available stock + safety stock per SKU-warehouse |
| `improved_forecast_30d.csv` | 60 | 30-day XGBoost demand forecasts |
| `scenario_stock_ageing.csv` | 240 | Age buckets (0-30, 31-60, 61-90, 90+ days) |
| `scenario_inbound_orders.csv` | 15 | Purchase orders with expected arrival dates |
| `transfer_routes.csv` | 6 | Inter-warehouse routes with cost + lead time |
| `disruptions.csv` | 2 | Component shortage + shipping route delay |

## 3. Forecasting Methodology

- **Model:** XGBoost regression
- **Features:** Temporal lags, day-of-week, warehouse/SKU encodings
- **Output:** 30-day daily demand forecast per SKU-warehouse (60 combos)
- **Note:** The forecast is pre-trained. What-if simulations **reuse** it unchanged — inventory and optimization are recalculated, but the forecast is not regenerated.

## 4. Inventory Risk Methodology

For each SKU-warehouse combo:
- **Unmet Demand** = `max(0, Forecast_30d − Available_Stock)`
- **Excess Stock** = `max(0, Available_Stock − Forecast_30d − Safety_Stock)`
- **Risk Classification:**
  - **Critical:** Unmet demand > 0
  - **Warning:** Available stock < 1.5x safety stock
  - **Excess:** Excess stock > 0
  - **Healthy:** None of the above

Total: Critical + Warning + Excess + Healthy = 60 combos.

Two unmet-demand figures exist:
- **~1,351 units** (static gap, Executive Dashboard): `max(0, Forecast_30d − Available_Stock)`
- **~1,119.7 units** (dynamic simulation, Transfer Optimization): daily simulation crediting inbound PO arrivals

## 5. Transfer Optimization Methodology

- **Method:** MILP via SciPy
- **Objective:** Minimize (unmet demand × margin) + transfer cost
- **Constraints:**
  - Transfer quantities are non-negative integers
  - Source retains safety stock (only excess is transferable)
  - No double-transfer of the same stock
  - Routes must exist in `transfer_routes.csv`
  - Lead times respected in daily simulation

### Demand Uncertainty Analysis

AI demand forecasts are not treated as absolute truth. The system estimates forecast
uncertainty from 875 out-of-sample test residuals in `test_predictions.csv`:

- `sigma_daily = std(Error)` = 2.00 units (daily residual standard deviation)
- `sigma_30d = sigma_daily * sqrt(30)` = 10.96 units (30-day horizon uncertainty)

Three demand scenarios are generated:
- **Low:** Forecast_30d − sigma_30d (clipped to non-negative)
- **Expected:** Forecast_30d (unchanged)
- **High:** Forecast_30d + sigma_30d

For each scenario, the full pipeline (risk → simulation → MILP → economics) is rerun.
The optimizer produces different recommendations: Low (22 transfers), Expected (28),
High (30). These are **empirical sensitivity bounds**, not calibrated prediction intervals.

## 6. Agent Orchestration

Six agents coordinated by `OrchestratorAgent`:
1. **ForecastingAgent** — loads XGBoost predictions
2. **InventoryRiskAgent** — shortage/excess/ageing analysis
3. **OptimizationAgent** — MILP solver
4. **ExplanationAgent** — deterministic business explanations
5. **ApprovalAgent** — SQLite approval workflow
6. **OrchestratorAgent** — coordinates pipeline

## 7. Results (Demonstration Scenario)

| Metric | Value |
|---|---|
| Recommended transfers | 28 |
| Total units recommended | 1,108 |
| Total transfer cost | 2,021.50 AED |
| Unmet demand before optimization | 1,119.7 units |
| Unmet demand after optimization | 12.4 units |
| Shortage reduction | 98.9% |
| Projected net economic benefit | 44,817.17 AED |

**All figures are projected estimates from simulation, not realized savings.**

## 8. Testing

`smoke_test.py` verifies (15 tests):
- Data loading and integrity
- Risk computation (60 combo classification)
- MILP optimizer (non-negative quantities, economic constraint)
- What-If simulation (inventory edit → recalc)
- Disruption simulation (component shortage + route delay)
- Ageing chart fix (label normalisation)
- Approval persistence (SQLite, audit trail, duplicate prevention)
- All page modules import
- All agent classes import
- Original datasets unchanged
- AI assistant ageing label normalisation (regression)
- Environment variable typo fix (regression)
- Dead code removal (regression)

`test_demand_uncertainty.py` verifies (14 tests):
- Low ≤ Expected ≤ High demand
- No negative demand predictions
- All three scenarios execute successfully
- Expected-demand results match existing baseline
- Inventory conservation maintained
- Transfer quantities non-negative integers
- Safety stock respected
- Route constraints valid
- Transfer costs recalculated correctly
- Economic benefits recalculated correctly
- Original datasets unchanged
- Sealed answer key not accessed
- Application loads new page
- Optimizer produces different recommendations per scenario

**Result: 15/15 smoke tests + 14/14 uncertainty tests passed.**

## 9. Limitations

- XGBoost forecast is pre-trained, not regenerated during what-if.
- Disruption simulation may show minimal impact when affected SKUs aren't in shortage.
- Demand uncertainty bounds are empirical sensitivity estimates, not statistically calibrated prediction intervals. The i.i.d. residual assumption likely understates true 30-day uncertainty.
- No live Tradeling integration.
- All benefits are simulated projections.
- Realized outcomes remain zero until physical execution.

## 10. Requirements for Real-World Deployment

- Live Tradeling API integration for inventory + demand data
- Automated daily forecast retraining pipeline
- ERP integration for transfer execution post-approval
- Role-based access control for approval workflow
- Real-time disruption monitoring and alerting
- Multi-objective optimization (cost, service level, ageing, carbon)
- Monte Carlo simulation for demand uncertainty
- Production database (PostgreSQL) replacing SQLite
