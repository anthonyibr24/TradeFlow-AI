# TradeFlow AI — Agentic AI-Powered Supply Chain Intelligence

**FutureMindz Tradeling Hackathon Submission**

TradeFlow AI is an agentic AI platform that forecasts demand, detects inventory risks, and recommends inter-warehouse transfers using mathematical optimization — with full human-in-the-loop approval.

https://tradeflow-ai-d3nvyizlyzgfy6jqvkmf4k.streamlit.app/

## Project Overview

Three warehouses (Dubai, Abu Dhabi, Sharjah) stock 20 SKUs. Demand is unevenly distributed, causing shortages at some locations while others hold excess. TradeFlow AI solves this by:

1. **Forecasting** 30-day demand per SKU-warehouse using XGBoost.
2. **Detecting** shortages, excess stock, and ageing risks.
3. **Optimizing** inter-warehouse transfers using MILP (SciPy).
4. **Explaining** each recommendation in business-friendly language.
5. **Requiring** human approval before any transfer is executed.

## Business Problem

- Inventory imbalances across warehouses cause lost sales (shortages) and tied-up capital (excess).
- Manual transfer decisions are slow and inconsistent.
- No visibility into ageing stock or economic exposure.

## Main Features

| Page | Description |
|---|---|
| **Executive Dashboard** | KPIs, risk distribution, warehouse comparison, AI insights |
| **Demand Forecasting** | XGBoost 30-day forecasts, accuracy metrics, model diagnostics |
| **Inventory Intelligence** | Risk table, ageing analysis, 30-day projections, AI explanations |
| **Transfer Optimization** | MILP recommendations, network graph, economic impact, before/after |
| **Agent Control Center** | Agent status, workflow log, **What-If Simulator**, **Disruption Simulator**, AI assistant |
| **Demand Uncertainty** | Three-scenario analysis (Low/Expected/High demand) with actual MILP rerun per scenario |
| **Approval Center** | Pending approvals, approve/reject, audit trail, approved-plan impact |

### What-If Scenario Simulator

Modify inventory levels for any SKU-warehouse combo and rerun:
- Inventory risk classification
- Expected unmet demand
- MILP transfer optimization
- Projected net economic benefit

The 30-day forecast is **reused unchanged** (not regenerated). Original CSV files are never modified.

### Supply-Chain Disruption Simulator

Uses actual `disruptions.csv` records:
- **Component Supply Shortage** — delays inbound orders for affected SKUs
- **Shipping Route Delay** — increases transfer lead time on affected routes
- **No Disruption** — baseline

### Demand Uncertainty Analysis

AI demand forecasts are not treated as absolute truth. The system uses empirical
test-set residuals from the XGBoost model to estimate forecast uncertainty and
generates three demand scenarios:

- **Low Demand:** Forecast_30d − sigma_30d (clipped to non-negative)
- **Expected Demand:** Forecast_30d (unchanged XGBoost forecast)
- **High Demand:** Forecast_30d + sigma_30d

**Uncertainty method:** 875 out-of-sample test predictions from `test_predictions.csv`
are used to compute `sigma_daily = std(Error)` and `sigma_30d = sigma_daily * sqrt(30)`.
This assumes i.i.d. daily residuals and is labeled as an **empirical sensitivity estimate**,
not a statistically calibrated prediction interval.

For each scenario, the system reruns:
1. Inventory risk calculation
2. Daily inventory simulation
3. MILP transfer optimization (different recommendations per scenario)
4. Transfer cost and projected net benefit calculation

**Results:** Values are computed dynamically per scenario and displayed on the Demand Uncertainty page. The comparison table shows forecast demand, unmet demand (before/after transfers), recommended transfers, and projected net benefit (AED) for each of the three scenarios.

## Agent Architecture

| Agent | Role |
|---|---|
| ForecastingAgent | Loads XGBoost predictions and accuracy metrics |
| InventoryRiskAgent | Analyzes shortages, excess, ageing |
| OptimizationAgent | Runs MILP solver for transfer recommendations |
| ExplanationAgent | Generates deterministic business explanations |
| ApprovalAgent | Manages human approval workflow with SQLite |
| OrchestratorAgent | Coordinates all agents |

## Machine Learning Approach

- **Model:** XGBoost regression
- **Features:** Temporal lags, day-of-week, warehouse/SKU encodings
- **Output:** 30-day daily demand forecast per SKU-warehouse (60 combos)
- **Accuracy:** MAPE, MAE, RMSE reported on forecast page

## Optimization Approach

- **Method:** Mixed-Integer Linear Programming (SciPy `linprog` / MILP)
- **Objective:** Minimize unmet demand + transfer cost
- **Constraints:**
  - Transfer quantities are non-negative integers
  - Source warehouses retain safety stock
  - No stock is transferred twice
  - Transfer routes must exist in `transfer_routes.csv`
  - Lead times are respected in daily simulation

## Dataset Descriptions

All data in the `Datasets/` directory:

| File | Description |
|---|---|
| `products.csv` | 20 SKUs with profit margins |
| `inventory.csv` | Original scenario inventory (overstocking) |
| `scenario_inventory.csv` | Demonstration scenario (inventory imbalance) |
| `stock_ageing.csv` | Original ageing buckets |
| `scenario_stock_ageing.csv` | Demonstration ageing buckets |
| `improved_forecast_30d.csv` | 30-day XGBoost forecasts (60 rows) |
| `improved_daily_forecasts.csv` | Daily forecast breakdown |
| `inbound_orders.csv` | Purchase orders with arrival dates |
| `scenario_inbound_orders.csv` | Demonstration inbound orders |
| `transfer_routes.csv` | Warehouse pairs with cost and lead time |
| `disruptions.csv` | Disruption records (component shortage, route delay) |

## Installation

```bash
pip install -r requirements.txt
```

## How to Run

```bash
streamlit run app.py
```

The app auto-discovers the data directory by checking:
1. `TRADEFLOW_DATA_DIR` environment variable (recommended)
2. `./data/` directory relative to the app
3. `./Datasets/` directory relative to the app

Set the `TRADEFLOW_DATA_DIR` environment variable if your data is elsewhere:

**Windows (PowerShell):**
```powershell
$env:TRADEFLOW_DATA_DIR = "C:\path\to\your\Datasets"
streamlit run app.py
```

**macOS/Linux:**
```bash
export TRADEFLOW_DATA_DIR="/path/to/your/Datasets"
streamlit run app.py
```

## Limitations

- The XGBoost forecast is pre-trained and **not regenerated** during what-if simulations.
- Disruption simulation delays inbound orders and transfer routes, but the dataset's affected SKUs may not be in shortage, resulting in minimal visible impact. This is an honest data limitation, not a bug.
- Two unmet-demand figures appear across pages: a **static gap** (forecast minus current stock) and a **dynamic simulation** figure (crediting inbound arrivals within the 30-day horizon). Both are correct — they measure different things. See the "Metric Definitions & Assumptions" section on the Agent Control Center page for current-scenario values.
- All economic benefits are **projected estimates from simulation**, not realized savings.
- No live integration with Tradeling or external APIs.

## Future Improvements

- Retrain XGBoost on the fly during what-if simulations.
- Real-time Tradeling API integration for live inventory sync.
- Multi-objective optimization (cost vs. service level vs. ageing).
- Automated transfer execution after approval (with ERP integration).
- Monte Carlo simulation for demand uncertainty.

## Testing

Run the smoke test:
```bash
python smoke_test.py
```

Tests verify: data loading, risk computation, MILP optimizer, what-if simulation, disruption simulation, ageing chart fix, approval persistence, dataset integrity, page imports, and agent imports.
