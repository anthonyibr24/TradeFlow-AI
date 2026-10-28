# TradeFlow AI — Comprehensive Technical & Functional Audit Report

**Date:** 2026-10-27  
**Auditor:** Automated + manual source code inspection  
**Method:** Read-only source code analysis, independent recalculation, controlled tests  
**No files were modified during this audit.**

---

## PHASE 1 — PROJECT ARCHITECTURE

### 1.1 Project Structure

```
20261027105634/
├── app.py                          # Streamlit entry point (st.navigation + st.Page)
├── simulation_engine.py            # What-If + Disruption simulation engine
├── smoke_test.py                   # 10 automated smoke tests
├── agent_system_tests.py           # Agent system tests
├── dashboard_tests.py              # Dashboard integration tests
├── components/
│   ├── metrics.py                  # Data loading + risk computation + AI insights
│   ├── charts.py                   # 15 Plotly chart functions
│   └── styling.py                  # CSS injection + KPI cards + color constants
├── pages/
│   ├── executive_dashboard.py      # Page 1: KPIs + charts + AI insights
│   ├── demand_forecasting.py       # Page 2: XGBoost forecast visualization
│   ├── inventory_intelligence.py   # Page 3: Risk table + ageing + projections
│   ├── transfer_optimization.py    # Page 4: MILP results + network graph
│   ├── agent_control_center.py     # Page 5: Agents + What-If + Disruption + AI assistant
│   └── approval_center.py          # Page 6: Approve/reject + audit trail
├── tradeflow_agents/
│   ├── __init__.py                 # Exports all agents
│   ├── database.py                 # SQLite schema + CRUD (AgentDatabase)
│   ├── forecast_agent.py           # ForecastingAgent
│   ├── inventory_agent.py          # InventoryRiskAgent
│   ├── optimization_agent.py       # OptimizationAgent (MILP)
│   ├── explanation_agent.py        # ExplanationAgent
│   ├── approval_agent.py           # ApprovalAgent
│   └── orchestrator.py             # OrchestratorAgent
├── Step2_Demand_Forecasting.ipynb  # XGBoost training pipeline
├── Step3_Inventory_Risk_Detection.ipynb
├── Step3_1_Inventory_Scenario.ipynb
├── Step4_Stock_Transfer_Optimization.ipynb
├── Step5_Agentic_AI_Demo.ipynb
├── README.md, HACKATHON_SUMMARY.md, DEMO_SCRIPT.md, requirements.txt
```

### 1.2 Agent Responsibilities (Verified)

| Agent | File | Actual Responsibility | Verified |
|---|---|---|---|
| ForecastingAgent | `forecast_agent.py` | Loads pre-trained XGBoost forecasts from CSV. Does NOT retrain. | ✅ |
| InventoryRiskAgent | `inventory_agent.py` | Merges inventory + forecast, classifies risk, computes shortages/excess/ageing | ✅ |
| OptimizationAgent | `optimization_agent.py` | Runs daily inventory simulation + MILP (scipy.optimize.milp) | ✅ |
| ExplanationAgent | `explanation_agent.py` | Generates deterministic text from optimization output. No LLM. | ✅ |
| ApprovalAgent | `approval_agent.py` | SQLite CRUD for recommendations + approvals. No inventory mutation. | ✅ |
| OrchestratorAgent | `orchestrator.py` | Coordinates sequential workflow. Caches last optimization result. | ✅ |

### 1.3 Data Flow (Verified)

```
CSV files → load_data() → data dict
    ↓
ForecastingAgent loads improved_forecast_30d.csv (pre-trained)
    ↓
InventoryRiskAgent merges inventory + forecast → risk classification
    ↓
OptimizationAgent._simulate_inventory() → daily projection → baseline unmet
    ↓
OptimizationAgent.get_transfer_recommendations() → MILP solver → 28 transfers
    ↓
ExplanationAgent → deterministic text from actual numbers
    ↓
ApprovalAgent → SQLite persistence → human approval
```

### 1.4 Technology Classification

| Feature | Technology | Evidence |
|---|---|---|
| Demand forecasting | **Machine Learning** (XGBoost) | Pre-trained model in `improved_forecast_30d.csv`. Training pipeline in `Step2_Demand_Forecasting.ipynb`. |
| Transfer optimization | **Mathematical Optimization** (MILP) | `scipy.optimize.milp` with HiGHS solver in `optimization_agent.py:565` |
| Inventory risk | **Deterministic rules** | `classify()` function in `metrics.py:87-94` |
| Explanations | **Deterministic templates** | `explanation_agent.py` — string interpolation from optimization output |
| AI Assistant | **Deterministic keyword matching** | `_answer_question()` in `agent_control_center.py:394` — no LLM API |
| Approval workflow | **SQLite CRUD** | `database.py` — standard SQL operations |

### 1.5 Agentic vs Orchestrated

**Finding: The system is primarily an orchestrated workflow, not genuinely agentic.**

- The OrchestratorAgent calls agents in a fixed sequential pipeline.
- Agents do not make autonomous decisions, negotiate, or adapt their strategy.
- Agents do not call each other; only the Orchestrator coordinates.
- The AI Assistant is a keyword-matching function, not an LLM-powered agent.
- No agent has tool-selection autonomy or reasoning loops.

This is not inherently bad for a hackathon, but claiming "agentic AI" is an overstatement. The system is a **modular orchestrated pipeline with deterministic agents**.

### 1.6 Unused Modules / Disconnected Features / Duplicate Calculations

| Issue | File | Details |
|---|---|---|
| **Unused method** | `optimization_agent.py:232` | `_calculate_transferable_stock()` is defined but never called. It also has a bug: reads from `self.scenario_inventory` regardless of scenario. The actual code uses the inner function `calc_transferable()` (line 379) which is correct. |
| **Dead code** | `optimization_agent.py:237-238` | `if self.data_dir and (sku, wh) in self.forecast_30d_map: pass` — no-op. |
| **Duplicate risk calculation** | `metrics.py:78` vs `inventory_agent.py:64` | Both compute risk classification independently. Results match but it's code duplication. |
| **GRAY color reference** | `charts.py:58,165` | `GRAY` is referenced but may not be imported — uses fallback `"#6B7280"`. |
| **Typo in env var** | `agent_control_center.py:118` | `_TRAFEFLOW_DATA_DIR` (should be `TRADEFLOW_DATA_DIR`). |

---

## PHASE 2 — DEMAND FORECASTING

### 2.1 XGBoost Training Pipeline (from notebook inspection)

| Check | Status | Evidence |
|---|---|---|
| Chronological train/validation split | ✅ VERIFIED | Notebook Section 2.1: "Chronological Data Splitting". Sales dates 2026-07-01 to 2026-09-28 (90 days). |
| No data leakage between train and forecast | ✅ VERIFIED | Sales history ends 2026-09-28. Forecast starts 2026-09-29. **0 overlapping dates.** |
| Sealed answer key not used during training | ⚠️ PARTIALLY VERIFIED | `future_demand_answer_key.csv` is **NOT FOUND** in the data directory. Cannot confirm existence or usage. The notebook does not reference it in training code. |
| Stockout handling | ✅ VERIFIED | Notebook implements 3 strategies for stockout-censored demand. Strategy 3 uses a demand proxy: `train_s3.loc[stockout_mask, "Demand_Proxy"] = causal_demand_proxy[stockout_mask]`. 85 stockout records, 78 have zero sales. |
| Missing record handling | ✅ VERIFIED | `Units_Sold_Imputed` column created. `Was_Missing` flag added. 109 missing records imputed. |

### 2.2 Forecast Generation

| Check | Status | Evidence |
|---|---|---|
| 30-day forecasts generated for 60 combos | ✅ VERIFIED | `improved_forecast_30d.csv`: 60 rows (20 SKUs × 3 warehouses) |
| Daily forecasts for 30 days | ✅ VERIFIED | `improved_daily_forecasts.csv`: 1800 rows (60 combos × 30 days) |
| Forecast date range | ✅ VERIFIED | 2026-09-29 to 2026-10-28 (30 days, no overlap with training) |
| Model selection | ✅ VERIFIED | All 60 combos use "Tuned XGBoost" |
| Uncertainty bounds | ✅ VERIFIED | Lower_Bound and Upper_Bound present. Avg range: 13.6 units (13.9% of forecast). |

### 2.3 Accuracy Verification

| Check | Status | Evidence |
|---|---|---|
| MAE, RMSE, WAPE independently recalculated | ❌ NOT TESTED | `future_demand_answer_key.csv` not found. Cannot compute accuracy metrics against ground truth. |
| Comparison against simple baseline | ✅ VERIFIED | Baseline (avg daily sales × 30) = 6,053.4 units. XGBoost = 6,385.1 units. Difference: +5.5%. XGBoost predicts slightly higher aggregate demand. |
| Model evaluation metrics file | ❌ NOT FOUND | `model_evaluation_metrics.csv`, `improved_model_metrics.csv`, `baseline_forecast_30d.csv` — all NOT FOUND in data directory. |

### 2.4 Weaknesses

1. **Cannot verify forecast accuracy** — the answer key and metrics files are missing from the data directory. The README claims "MAPE, MAE, RMSE reported on forecast page" but the forecast page (`demand_forecasting.py`) does not display these metrics from a file — it would need to compute them, and without ground truth, it cannot.
2. **Pre-trained only** — forecasts are loaded from CSV, not regenerated. This is correctly labeled in the what-if simulator.
3. **Aggregate forecast is 5.5% higher than baseline** — this could indicate the model learned an upward trend, or that stockout imputation inflated training targets.

---

## PHASE 3 — INVENTORY INTELLIGENCE

### 3.1 Verification Results

| Check | Status | Evidence |
|---|---|---|
| 20 SKUs × 3 warehouses = 60 combos | ✅ VERIFIED | `scenario_inventory.csv`: 60 rows |
| Static unmet demand independently recalculated | ✅ VERIFIED | `max(0, Forecast_30d − Available_Stock)` = **1,351.1 units** |
| Dynamic unmet demand (from projection CSV) | ✅ VERIFIED | `scenario_daily_inventory_projection.csv` grouped by SKU/warehouse = **1,119.7 units** |
| Difference explained | ✅ VERIFIED | Static (1,351.1) > Dynamic (1,119.7) because dynamic simulation credits inbound arrivals during the 30-day horizon. Difference = 231.4 units. |
| Pre-computed CSV matches dynamic | ✅ VERIFIED | `scenario_inventory_risks.csv` Expected_Unmet_Demand total = 1,119.7 (matches dynamic projection) |
| Risk classification sums to 60 | ✅ VERIFIED | Critical: 32, Excess: 19, Healthy: 9, Warning: 0. Total: 60. |
| Excess stock | ✅ VERIFIED | 5,385.3 units above forecast + safety |
| Safety stock handling | ✅ VERIFIED | `Safety_Stock` column in inventory CSV, used in classification and transferable stock calculation |
| Inbound purchase orders | ✅ VERIFIED | 15 orders, 873 units total, arriving 2026-10-01 to 2026-10-19 |
| Ageing data | ✅ VERIFIED | 240 rows (60 combos × 4 buckets). Buckets: "0-30 days", "31-60 days", "61-90 days", "90+ days" |

### 3.2 The 1,351 vs 1,119.7 Discrepancy — Root Cause

**VERIFIED — This is not a bug. It is a legitimate difference in calculation methodology:**

| Metric | Value | Formula | Where Used |
|---|---|---|---|
| Static unmet demand | 1,351.1 | `max(0, Forecast_30d − Available_Stock)` | Executive Dashboard (`compute_risk_summary`) |
| Dynamic unmet demand | 1,119.7 | Daily simulation: `Σ daily max(0, demand_t − stock_t)` where `stock_t` includes inbound arrivals | Transfer Optimization (`_simulate_inventory`) |

The dynamic figure is lower because inbound purchase orders (873 units total) arrive during the 30-day horizon and are credited to stock before computing daily unmet demand.

### 3.3 Inconsistent Calculations Across Pages

| Issue | Status | Impact |
|---|---|---|
| Executive Dashboard shows 1,351 unmet | ✅ EXPLAINED | Uses static calculation (simpler, no inbound modeling) |
| Transfer Optimization shows 1,119.7 unmet | ✅ EXPLAINED | Uses dynamic daily simulation (credits inbound) |
| Both are correct for their context | ✅ VERIFIED | Explanation added to Agent Control Center page |

### 3.4 Ageing Chart Label Fix

**VERIFIED — The fix works correctly.**

The CSV contains `"0-30 days"` but the chart code originally expected `"0-30"`. The fix (`df["Age_Bucket"] = df["Age_Bucket"].str.replace(" days", "", regex=False)`) normalizes the labels. Both `ageing_chart()` and `ageing_by_sku()` were fixed.

Test output confirms: chart x values = `['0-30', '31-60', '61-90', '90+']`, y values = `[2726, 2537, 2812, 2861]`.

---

## PHASE 4 — TRANSFER OPTIMIZATION

### 4.1 MILP Inspection

| Check | Status | Evidence |
|---|---|---|
| Uses `scipy.optimize.milp` (HiGHS solver) | ✅ VERIFIED | `optimization_agent.py:19,565` |
| Objective: maximize net benefit (minimize negative) | ✅ VERIFIED | `c_obj[i] = -c_row["Net_Benefit_Per_Unit_AED"]` (line 514) |
| Integer constraint on transfer quantities | ✅ VERIFIED | `integrality = np.ones(n_vars)` (line 563) |
| Non-negative bounds | ✅ VERIFIED | `bounds = Bounds(lb=0, ub=np.array(var_ub))` (line 562) |
| Source capacity constraint (transferable stock) | ✅ VERIFIED | Lines 530-541: `Σ transfers from source ≤ transferable_stock` |
| Destination constraint (don't exceed unmet) | ✅ VERIFIED | Lines 543-554: `Σ transfers to destination ≤ unmet_demand` |
| Route feasibility check | ✅ VERIFIED | Line 339: `if route_key not in self.route_map: continue` |
| Lead time in transfer arrival | ✅ VERIFIED | Line 433: `arrival_day = self.horizon_start + timedelta(days=int(c["Lead_Time_Days"]))` |
| Reducible unmet filter (arrive before shortage) | ✅ VERIFIED | Lines 442-450: Only counts unmet that occurs after transfer arrival |

### 4.2 Constraint Verification

| Check | Status | Result |
|---|---|---|
| Transfer quantities non-negative | ✅ VERIFIED | All 28 recs have qty ≥ 0. Min: 20, Max: 116 |
| Transfer quantities are integers | ✅ VERIFIED | dtype: int64 |
| Route feasibility | ✅ VERIFIED | 0 invalid routes out of 28 |
| Source inventory conservation | ✅ VERIFIED | 0 violations. All sources within transferable limit. |
| Safety stock preserved | ✅ VERIFIED | `calc_transferable` = `max(0, available - forecast - safety)` — only excess above forecast + safety is transferable |
| No double-counting | ✅ VERIFIED | Source groups aggregate all outgoing transfers per (SKU, source) and cap at transferable |
| Transfer cost calculation | ✅ VERIFIED | `transfer_cost = qty * cost_per_unit`. Total: 2,021.50 AED |

### 4.3 Independent Recalculation

| Metric | Claimed | Independently Verified | Match |
|---|---|---|---|
| Number of transfers | 28 | 28 (CSV row count) | ✅ |
| Total units | 1,108 | 1,108 (CSV sum) | ✅ |
| Total transfer cost | 2,021.50 AED | 2,021.50 AED (CSV sum) | ✅ |
| Baseline unmet (dynamic) | 1,119.7 | 1,119.7 (projection CSV) | ✅ |
| Post-transfer unmet | 12.4 | 12.4 (post_transfer_projection CSV) | ✅ |
| Unmet reduction | 98.9% | (1119.7−12.4)/1119.7 = 98.9% | ✅ |
| Net economic benefit | 44,817.17 AED | margin_preserved (46,838.67) − cost (2,021.50) = 44,817.17 | ✅ |

### 4.4 Economic Calculation Verification

**VERIFIED — `Net Benefit = Margin Preserved − Transfer Cost`**

- From optimization summary CSV: `Estimated margin preserved: 46,838.67 AED`
- `Total transfer cost: 2,021.50 AED`
- `Net economic benefit: 46,838.67 − 2,021.50 = 44,817.17 AED` ✅

**Note:** The transfer recommendations CSV sums to a different net benefit (36,890.15 AED) because the CSV stores per-recommendation `Estimated_Net_Benefit_AED` which uses `unmet_avoided * margin - cost`, while the summary uses `actual_margin_preserved` from the post-transfer simulation (which accounts for the actual reduction in unmet demand, not the per-rec estimate). This is explained by the `step4_discrepancy_note` in the optimization result.

### 4.5 Unrealistic Assumptions

1. **Transfers dispatched at horizon start** — all transfers depart simultaneously on day 0. In reality, dispatch would be staggered.
2. **Fixed lead time** — no variability in transfer time.
3. **No demand surges or simultaneous disruptions** — single-scenario optimization.
4. **Daily demand follows XGBoost point forecast** — no Monte Carlo or probabilistic simulation.
5. **All surplus is transferable** — assumes stock is available in the right condition and packaging.

---

## PHASE 5 — LIVE WHAT-IF SIMULATOR

### 5.1 Test Results

| Test | Status | Result |
|---|---|---|
| Increase inventory (SKU-003 Dubai 43→209) | ✅ VERIFIED | Baseline unmet: 1,351.1 → Modified: 1,234.4. Unmet decreased by 116.7 units. Recs: 28→27 (one transfer eliminated). |
| Decrease inventory (SKU-003 Dubai 43→10) | ✅ VERIFIED | Baseline unmet: 1,351.1 → Modified: 1,384.1. Unmet increased by 33.0 units. |
| Extreme value (100,000) | ✅ VERIFIED | No crash. Returns valid result. |
| Invalid SKU | ✅ VERIFIED | Returns error: "SKU INVALID / Warehouse Dubai not found in inventory." |
| Change safety stock (50→200) | ✅ VERIFIED | Safety stock change recorded. old=32, new=200. |
| Original files preserved | ✅ VERIFIED | `scenario_inventory.csv` unchanged after simulation |
| Forecast reused (not regenerated) | ✅ VERIFIED | `forecast_note` explicitly states forecast was NOT regenerated |

### 5.2 Propagation Verification

| Check | Status | Evidence |
|---|---|---|
| Inventory modification propagates to risk | ✅ VERIFIED | `compute_risk_summary(modified_inv, forecast_30d)` — unmet changes |
| Inventory modification propagates to MILP | ✅ VERIFIED | `_SimulationOptimizer` subclasses `OptimizationAgent`, overrides `_get_inventory()`. MILP reruns on modified data. |
| Before/after financial metrics consistent | ✅ VERIFIED | Baseline and modified KPIs both computed from actual optimization output |
| Reset behavior | ✅ VERIFIED | Reset button clears `whatif_result` from session state |

### 5.3 Issues

1. **No explicit reset of inventory to original values** — reset clears the result display but doesn't re-select original values in the number inputs. The user must manually change them back.
2. **Typo in env var name** — `_TRAFEFLOW_DATA_DIR` instead of `TRADEFLOW_DATA_DIR` in `agent_control_center.py:118`.

---

## PHASE 6 — DISRUPTION SIMULATOR

### 6.1 Disruption Data

| Disruption | ID | Type | Affected | Delay |
|---|---|---|---|---|
| Component Shortage | D001 | Component Shortage | SKU-001, SKU-002, SKU-003 | 10 days |
| Shipping Route Delay | D002 | Shipping Route Delay | Dubai→Abu Dhabi route | 5 days |

### 6.2 Test Results

| Test | Status | Result |
|---|---|---|
| Component Supply Shortage | ⚠️ PARTIALLY VERIFIED | Runs without error. Delays 4 inbound orders by 10 days. **But produces identical results to baseline.** |
| Shipping Route Delay | ⚠️ PARTIALLY VERIFIED | Runs without error. Increases Dubai→Abu Dhabi lead time from 1 to 6 days. **But produces identical results to baseline.** |
| No Disruption | ✅ VERIFIED | Returns baseline correctly |

### 6.3 Root Cause Analysis — Why Component Shortage Produces Identical Results

**VERIFIED — This is a data limitation, not an implementation defect.**

The `_SimulationOptimizer` correctly:
1. Delays inbound orders for SKU-001, SKU-002, SKU-003 by 10 days
2. The modified inbound map shows different arrival dates
3. The simulation processes the modified inbound

**But the unmet demand doesn't change because:**

| Affected SKU/Warehouse | Has Inbound? | In Shortage? | Impact of Delay |
|---|---|---|---|
| SKU-001/Dubai | Yes (70 units, 10/06→10/16) | No (avail=166, fc=121.5) | None — no shortage to worsen |
| SKU-002/Abu Dhabi | Yes (52 units, 10/06→10/16) | No (avail=182, fc=74.6) | None — no shortage |
| SKU-003/Abu Dhabi | Yes (81 units, 10/19→10/29) | No (avail=550, fc=159.7) | Delayed order falls outside horizon (10/29 > 10/28), but no shortage anyway |
| SKU-003/Sharjah | Yes (85 units, 10/07→10/17) | No (avail=115, fc=138.3) | None — surplus stock |
| SKU-003/Dubai | No inbound | Yes (avail=43, fc=159.7, unmet=116.7) | Not affected — no inbound to delay |
| SKU-002/Sharjah | No inbound | Yes (avail=17, fc=62.0, unmet=45.0) | Not affected — no inbound to delay |

**Root cause:** The SKUs in shortage (SKU-003/Dubai, SKU-002/Sharjah) have **no inbound orders** in the scenario data. Delaying inbound orders for other SKUs that aren't in shortage has no effect on unmet demand.

### 6.4 Root Cause — Why Shipping Route Delay Produces Identical Results

The Dubai→Abu Dhabi route is used by some transfers, but increasing the lead time from 1 to 6 days doesn't change which transfers are recommended or their quantities because:
1. The MILP optimizes based on net benefit per unit, not arrival timing (arrival only filters "reducible unmet")
2. With a 6-day lead time, transfers still arrive within the 30-day horizon
3. The cumulative unmet demand after day 6 is still sufficient to justify the same transfers

### 6.5 Controlled Test Design

A test case that **should** produce a measurable impact:
- Select a SKU-warehouse combo that IS in shortage AND HAS an inbound order arriving early in the horizon
- Delay that inbound by enough days to push it past the stockout date
- This should increase unmet demand

**Finding:** No such combo exists in the current dataset. The shortage combos (SKU-003/Dubai, SKU-002/Sharjah) have no inbound orders. This is a **dataset limitation**.

### 6.6 Honest Labeling

The UI includes a warning when delta is <0.1:
> "This disruption had minimal impact on the projected outcomes. The affected SKUs/routes may not be in shortage, or the delayed inbound orders may arrive outside the 30-day simulation horizon. This is an honest result from the actual data — not a bug."

**Status: The simulator works correctly but the dataset doesn't produce meaningful disruption impact. This is honestly labeled.**

---

## PHASE 7 — AGENT SYSTEM

### 7.1 Agent Verification

| Agent | Initializes | Executes Tools | Handles Errors | Adapts to New Inputs |
|---|---|---|---|---|
| ForecastingAgent | ✅ | ✅ Loads CSV data | ✅ Returns error dict for missing SKU | ❌ No adaptation — static data |
| InventoryRiskAgent | ✅ | ✅ Computes risk from data | ✅ Unknown scenario returns error | ❌ No adaptation |
| OptimizationAgent | ✅ | ✅ Runs MILP solver | ✅ Multiple early-return paths for edge cases | ✅ Works with modified inventory (via subclass) |
| ExplanationAgent | ✅ | ✅ Generates deterministic text | ✅ Missing recommendation returns error | ❌ Template-based |
| ApprovalAgent | ✅ | ✅ SQLite CRUD | ✅ Invalid ID, duplicate prevention | ✅ Handles new recommendations |
| OrchestratorAgent | ✅ | ✅ Coordinates all agents | ✅ Invalid scenario returns error | ✅ Supports individual agent calls |

### 7.2 AI Supply Chain Assistant Tests

| Question | Status | Answer Quality |
|---|---|---|
| "Which warehouse has the highest shortage risk?" | ✅ VERIFIED | Correct: "Dubai has the highest projected unmet demand at 576 units" |
| "What products should we transfer?" | ✅ VERIFIED | Correct: Lists top 5 transfers with actual data |
| "How much money could the proposed transfers save?" | ✅ VERIFIED | Correct: "44,817 AED net benefit, 2,022 AED cost, 46,839 AED margin" |
| "Which warehouse has the most ageing inventory?" | ⚠️ PARTIALLY VERIFIED | Returns "No significant aged inventory detected" — but ageing data shows 2,861 units in 90+ bucket. **Bug: the function checks `["61-90", "90+"]` but CSV has `["61-90 days", "90+ days"]`.** |
| "What is the coverage ratio?" | ✅ VERIFIED | Correct: "1.71x the 30-day forecast demand" |

### 7.3 Misleading Claims About Agent Autonomy

| Claim | Reality |
|---|---|
| "Agentic AI" | Orchestrated pipeline with deterministic agents |
| "AI Supply Chain Assistant" | Keyword-matching function, no LLM |
| "Agent adapts to new inputs" | Only the What-If simulator adapts (via subclass); agents themselves are static |

---

## PHASE 8 — HUMAN APPROVAL

### 8.1 Verification Results

| Check | Status | Result |
|---|---|---|
| Approve a recommendation | ✅ VERIFIED | `approve_transfer()` returns success, status changes to "Approved" |
| Reject a recommendation | ✅ VERIFIED | `reject_transfer()` returns success, status changes to "Rejected" |
| SQLite persistence | ✅ VERIFIED | New `AgentDatabase` instance reads same status |
| Duplicate approval prevention | ✅ VERIFIED | Second approval returns `success: False, error: "Duplicate approval prevented"` |
| Approve after rejection prevention | ✅ VERIFIED | Returns `success: False, error: "Cannot approve a rejected transfer"` |
| Audit trail | ✅ VERIFIED | 4 entries in audit_log table with timestamp, agent, action, details |
| Approvals don't modify inventory | ✅ VERIFIED | `scenario_inventory.csv` unchanged after approval |
| Scenario isolation | ✅ VERIFIED | Demonstration recs and original recs are separate; `clear_recommendations(scenario)` clears only one scenario |
| Recommendations not approved twice | ✅ VERIFIED | `update_approval_status` checks `old_status == status` and `old_status in ("Approved", "Rejected")` |
| Stale recommendations | ✅ VERIFIED | `load_recommendations` clears existing recs for the scenario before loading new ones |

### 8.2 Finding

The approval system is **well-designed and correctly implemented**. It properly distinguishes between:
- Proposed transfers (optimization output)
- Approved transfers (human-approved subset)
- Rejected transfers (human-rejected subset)
- Pending transfers (awaiting decision)

No inventory mutation occurs upon approval — purely a decision-tracking system.

---

## PHASE 9 — STREAMLIT USER INTERFACE

### 9.1 Page-by-Page Inspection (Source Code Only — Not Rendered)

| Page | Import Check | Key Issues |
|---|---|---|
| Executive Dashboard | ✅ Imports | Uses static unmet (1,351) — may confuse users who see 1,119.7 on Transfer Optimization page |
| Demand Forecasting | ✅ Imports | No accuracy metrics displayed (files not found). Claims "MAPE, MAE, RMSE" in README but page doesn't show them |
| Inventory Intelligence | ✅ Imports | Ageing chart label fix applied. Uses correct scenario data |
| Transfer Optimization | ✅ Imports | Shows CSV-based recommendations (28 recs). Has discrepancy explanation expander |
| Agent Control Center | ✅ Imports | What-If + Disruption simulators functional. AI assistant works. Metric definitions section added |
| Approval Center | ✅ Imports | Approve/reject buttons work. Audit trail displayed. Regenerate button available |

### 9.2 UI Issues (From Source Code Inspection)

| Issue | Severity | File | Details |
|---|---|---|---|
| Ageing chart label mismatch (FIXED) | ✅ Fixed | `charts.py:308,336` | `" days"` suffix stripped |
| White labels on white background | ⚠️ Low | `charts.py` | `_LAYOUT` sets `font color="#111827"` (dark) and `paper_bgcolor="white"` — should be fine |
| KPI inconsistency | ⚠️ Medium | `executive_dashboard.py:87` | Shows 1,351 unmet (static) while Transfer Optimization shows 1,119.7 (dynamic) — explained but still confusing |
| No accuracy metrics on forecast page | ⚠️ Medium | `demand_forecasting.py` | README claims MAPE/MAE/RMSE but files not found |
| Ageing question in AI assistant returns wrong answer | ⚠️ Medium | `agent_control_center.py:478-480` | Checks `["61-90", "90+"]` but CSV has `["61-90 days", "90+ days"]` |
| Mobile layout | ❌ NOT TESTED | — | Cannot verify without rendering |

### 9.3 Session State Behavior

| Check | Status | Evidence |
|---|---|---|
| Scenario persists across pages | ✅ VERIFIED | `st.session_state["scenario"]` set in `app.py:59` |
| Data dir persists | ✅ VERIFIED | `st.session_state["data_dir"]` set in `app.py:61` |
| What-if result persists within session | ✅ VERIFIED | Stored in `st.session_state["whatif_result"]` |
| Disruption result persists within session | ✅ VERIFIED | Stored in `st.session_state["disruption_result"]` |
| Chat history persists | ✅ VERIFIED | Stored in `st.session_state["chat_messages"]` |

---

## PHASE 10 — HACKATHON COMPLIANCE MATRIX

| # | Requirement | Evidence in Code | Test Performed | Status | Gap |
|---|---|---|---|---|---|
| 1 | Demand forecasting with ML | XGBoost in `Step2_Demand_Forecasting.ipynb`, `improved_forecast_30d.csv` | Verified forecast output (60 rows, 30 days) | ✅ VERIFIED | Accuracy metrics files missing |
| 2 | 30-day forecast for 20 SKUs × 3 warehouses | `improved_forecast_30d.csv`: 60 rows | Row count verified | ✅ VERIFIED | None |
| 3 | Inventory shortage detection | `compute_risk_summary()` in `metrics.py` | Independently recalculated (1,351.1 static) | ✅ VERIFIED | None |
| 4 | Excess stock detection | `compute_risk_summary()` | Independently recalculated (5,385.3 units) | ✅ VERIFIED | None |
| 5 | Ageing detection | `scenario_stock_ageing.csv` + chart functions | Ageing chart verified (label fix applied) | ✅ VERIFIED | None |
| 6 | MILP transfer optimization | `scipy.optimize.milp` in `optimization_agent.py` | 28 transfers verified, constraints checked | ✅ VERIFIED | None |
| 7 | Six modular agents | 6 agent classes in `tradeflow_agents/` | All import successfully | ✅ VERIFIED | Not genuinely "agentic" — orchestrated |
| 8 | Agent orchestration | `OrchestratorAgent` in `orchestrator.py` | `run_full_workflow()` tested | ✅ VERIFIED | Sequential, not adaptive |
| 9 | Explainable recommendations | `ExplanationAgent` | Deterministic text from actual data | ✅ VERIFIED | No LLM reasoning |
| 10 | SQLite approval management | `AgentDatabase` + `ApprovalAgent` | Approve/reject/persist/duplicate-prevent tested | ✅ VERIFIED | None |
| 11 | Two predefined scenarios | "demonstration" + "original" | Both load and compute correctly | ✅ VERIFIED | None |
| 12 | What-If Simulator | `simulation_engine.py` + UI in `agent_control_center.py` | 5 test cases passed | ✅ VERIFIED | No reset of input values |
| 13 | Disruption Simulator | `run_disruption_simulation()` | Runs but produces no measurable impact | ⚠️ PARTIALLY VERIFIED | Dataset limitation — affected SKUs not in shortage |
| 14 | Data consistency (unmet demand) | Explanation in Agent Control Center | Root cause identified and explained | ✅ EXPLAINED | Static vs dynamic — both correct |
| 15 | Risk classification = 60 combos | `compute_risk_summary()` | 32+0+19+9 = 60 | ✅ VERIFIED | None |
| 16 | Net benefit = margin − cost | Optimization summary | 46,838.67 − 2,021.50 = 44,817.17 | ✅ VERIFIED | None |
| 17 | Original datasets unchanged | What-if/disruption use working copies | File integrity verified after tests | ✅ VERIFIED | None |
| 18 | No physical transfer execution | Approval only updates SQLite | Inventory CSV unchanged after approval | ✅ VERIFIED | None |
| 19 | AED currency | All financial values in AED | Verified in products, routes, recommendations | ✅ VERIFIED | None |
| 20 | Transfer quantities non-negative integers | MILP bounds + integrality | All 28 recs: int64, min=20, max=116 | ✅ VERIFIED | None |
| 21 | Route feasibility | `route_map` lookup | 0 invalid routes | ✅ VERIFIED | None |
| 22 | Safety stock constraints | `calc_transferable` subtracts safety | 0 violations | ✅ VERIFIED | None |
| 23 | Lead times respected | `arrival_day` computation | Transfers arrive within horizon | ✅ VERIFIED | None |

---

## PHASE 11 — FINAL REPORT

### A. Overall Project Readiness Score

**Score: 78 / 100**

| Criterion | Weight | Score | Weighted | Justification |
|---|---|---|---|---|
| Demand Forecasting | 15 | 12 | 1.80 | XGBoost trained with chronological split, no leakage, stockout handling. But accuracy metrics files missing. |
| Inventory Intelligence | 15 | 14 | 2.10 | All calculations verified correct. Ageing chart fixed. Discrepancy explained. |
| Transfer Optimization | 20 | 19 | 3.80 | MILP solver works correctly. All constraints verified. Economic calculation correct. Minor: unused dead code. |
| What-If Simulator | 15 | 13 | 1.95 | Works correctly for all test cases. Propagates through risk + MILP. Minor: env var typo, no input reset. |
| Disruption Simulator | 10 | 5 | 0.50 | Implementation is correct but produces no measurable impact due to dataset limitation. Honestly labeled. |
| Agent System | 10 | 7 | 0.70 | All 6 agents work. But not genuinely agentic — orchestrated pipeline. AI assistant ageing answer is buggy. |
| Human Approval | 10 | 10 | 1.00 | Fully functional. SQLite persistence, duplicate prevention, audit trail, scenario isolation. |
| UI / Documentation | 5 | 4 | 0.20 | 6 pages functional. README/HACKATHON_SUMMARY/DEMO_SCRIPT created. Accuracy metrics not displayed. |

### B. Feature Verification Table

| Feature | Status | Evidence | Issue |
|---|---|---|---|
| XGBoost demand forecasting | ✅ VERIFIED | 60 forecasts, 30 days, no leakage | Accuracy metrics files missing |
| Inventory risk classification | ✅ VERIFIED | 60 combos, sums correctly | None |
| Static unmet demand (1,351) | ✅ VERIFIED | Independently recalculated | Different from dynamic — explained |
| Dynamic unmet demand (1,119.7) | ✅ VERIFIED | Matches projection CSV | None |
| MILP transfer optimization | ✅ VERIFIED | 28 transfers, all constraints | None |
| Economic benefit calculation | ✅ VERIFIED | 44,817.17 = 46,838.67 − 2,021.50 | None |
| What-If simulator | ✅ VERIFIED | 5 test cases passed | Env var typo, no input reset |
| Disruption simulator | ⚠️ PARTIALLY VERIFIED | Runs but no impact | Dataset limitation |
| Ageing chart | ✅ VERIFIED (FIXED) | Label fix applied | None |
| Approval workflow | ✅ VERIFIED | Full CRUD + persistence | None |
| AI assistant | ⚠️ PARTIALLY VERIFIED | 4/5 questions correct | Ageing answer wrong (label mismatch) |
| Agent orchestration | ✅ VERIFIED | Sequential pipeline works | Not genuinely agentic |

### C. Critical Bugs That Could Invalidate Results

| # | Bug | File | Line | Impact | Severity |
|---|---|---|---|---|---|
| C1 | AI assistant ageing question checks `["61-90", "90+"]` but CSV has `["61-90 days", "90+ days"]` | `agent_control_center.py` | 480 | Returns "No significant aged inventory detected" when 5,673 units are aged 60+ days | Medium |
| C2 | Env var typo `TRAFEFLOW_DATA_DIR` instead of `TRADEFLOW_DATA_DIR` | `agent_control_center.py` | 118 | What-If simulator may not find data dir if relying on env var | Low (fallback path exists) |
| C3 | Unused `_calculate_transferable_stock()` reads from wrong scenario | `optimization_agent.py` | 236 | No impact — method never called. Dead code. | Very Low |
| C4 | Missing accuracy metrics files | Data directory | — | Cannot verify forecast accuracy (MAE/RMSE/WAPE) | Medium |

### D. Important Improvements (High ROI)

| # | Improvement | Effort | Impact |
|---|---|---|---|
| I1 | Fix AI assistant ageing label mismatch (same fix as chart) | 5 min | Correct answer for ageing question |
| I2 | Fix env var typo | 1 min | Env var override works |
| I3 | Remove dead `_calculate_transferable_stock()` method | 2 min | Code cleanliness |
| I4 | Add forecast accuracy metrics to Demand Forecasting page (compute from validation set) | 30 min | Substantiates ML claims |
| I5 | Make disruption simulator produce measurable impact by testing with a SKU that has both shortage and inbound orders | 20 min | Demonstrates disruption simulation value |

### E. Minor Cosmetic Improvements

| # | Improvement |
|---|---|
| M1 | Add a "Reset to original values" button for What-If simulator that also resets number inputs |
| M2 | Display static vs dynamic unmet demand side-by-side on Executive Dashboard |
| M3 | Add tooltips explaining the difference between static and dynamic unmet demand |

### F. Files and Functions Responsible for Each Issue

| Issue | File | Function/Line |
|---|---|---|
| C1: Ageing label mismatch in AI assistant | `pages/agent_control_center.py` | `_answer_question()`, line 480 |
| C2: Env var typo | `pages/agent_control_center.py` | Line 118 |
| C3: Dead code | `tradeflow_agents/optimization_agent.py` | `_calculate_transferable_stock()`, line 232-241 |
| C4: Missing metrics | Data directory | `future_demand_answer_key.csv`, `model_evaluation_metrics.csv` not found |
| Disruption no-impact | `scenario_inbound_orders.csv` | Affected SKUs (001,002,003) not in shortage where they have inbound orders |
| I1 fix location | `pages/agent_control_center.py` | Line 480: add `.str.replace(" days", "")` |

### G. Prioritized Improvement Plan

#### P0 — Critical Correctness Issues

| # | Task | File | Time |
|---|---|---|---|
| P0-1 | Fix AI assistant ageing label mismatch | `agent_control_center.py:480` | 5 min |

#### P1 — High-Value Improvements

| # | Task | File | Time |
|---|---|---|---|
| P1-1 | Fix env var typo | `agent_control_center.py:118` | 1 min |
| P1-2 | Remove dead `_calculate_transferable_stock()` | `optimization_agent.py:232-241` | 2 min |
| P1-3 | Design disruption test case with measurable impact (e.g., delay inbound for a SKU in shortage) | `simulation_engine.py` + test | 20 min |
| P1-4 | Add forecast validation metrics to Demand Forecasting page | `demand_forecasting.py` | 30 min |

#### P2 — Optional Enhancements

| # | Task | Time |
|---|---|---|
| P2-1 | Add "Reset to original values" button for What-If inputs | 10 min |
| P2-2 | Display both static and dynamic unmet on Executive Dashboard | 15 min |
| P2-3 | Add Monte Carlo demand simulation | 2+ hours |
| P2-4 | Make agents genuinely agentic (tool selection, reasoning) | 4+ hours |

### H. Exact Commands to Reproduce Tests

```bash
# Smoke test (10 tests)
cd "c:\Users\antho\CodeBuddy\20261027105634"
python smoke_test.py

# Agent system tests
python agent_system_tests.py

# Dashboard integration tests
python dashboard_tests.py

# Run the application
streamlit run app.py
```

### I. Final Recommendation

**The prototype is technically ready for submission with one P0 fix needed.**

**Strengths:**
- MILP optimization is correctly implemented with all constraints verified
- What-If simulator works correctly — actual backend recalculation, not frontend-only
- Approval workflow is robust with SQLite persistence and proper duplicate prevention
- All economic calculations are verified correct
- No data leakage in the forecasting pipeline
- Original datasets are never modified
- Results are honestly labeled as projected/simulated

**Weaknesses:**
- Disruption simulator produces no measurable impact (dataset limitation, honestly labeled)
- Forecast accuracy cannot be independently verified (metrics files missing)
- System is orchestrated, not genuinely agentic
- AI assistant has one buggy answer (ageing label mismatch)

**Recommendation:** Fix P0-1 (ageing label in AI assistant, 5 minutes), then submit. The disruption simulator limitation is honestly labeled and the core optimization + what-if + approval functionality is solid.
