# Demand Uncertainty Analysis — Final Report

## A. Files Created or Modified

### Created
| File | Description |
|---|---|
| `demand_uncertainty.py` | Demand uncertainty engine: residual-based uncertainty estimation, three-scenario generation, MILP rerun per scenario |
| `pages/demand_uncertainty.py` | Streamlit page: scenario comparison table, visualizations, interactive selection, explanation panel |
| `test_demand_uncertainty.py` | 14 automated tests for mathematical correctness |

### Modified
| File | Change |
|---|---|
| `app.py` | Added `page_demand_uncertainty()` function and registered page in navigation |
| `README.md` | Added Demand Uncertainty page to feature table and methodology section |
| `HACKATHON_SUMMARY.md` | Added uncertainty methodology, updated testing section (15+14 tests) |
| `DEMO_SCRIPT.md` | Added 4:00-4:40 Demand Uncertainty demo section |

### NOT Modified
- Original datasets (verified by MD5 hash)
- Forecasting calculations
- Optimization constraints (MILP objective, bounds, integrality)
- Financial metrics
- Existing baseline results

## B. Uncertainty Estimation Method

**Data source:** `test_predictions.csv` — 875 out-of-sample predictions from the XGBoost model's test period (days 76-90 of sales history).

**Method:**
1. Compute daily residuals: `Error = Actual - Predicted` for each test prediction
2. `sigma_daily = std(Error)` = **2.00 units** (daily residual standard deviation)
3. `sigma_30d = sigma_daily * sqrt(30)` = **10.96 units** (30-day horizon uncertainty)

**Three scenarios:**
- **Low Demand:** `Forecast_30d - sigma_30d` (per combo, clipped to non-negative)
- **Expected Demand:** `Forecast_30d` (unchanged XGBoost forecast)
- **High Demand:** `Forecast_30d + sigma_30d`

**Supporting evidence:**
- 875 out-of-sample test predictions with Error and Abs_Error columns
- Chronological train/validation/test split in notebook (train: days 1-60, validation: 61-75, test: 76-90)
- No data leakage (sales history ends 2026-09-28, forecast starts 2026-09-29)
- The sealed `future_demand_answer_key.csv` is never accessed

**Classification:** Empirical sensitivity estimate — NOT a statistically calibrated prediction interval. The i.i.d. residual assumption likely understates true 30-day uncertainty.

## C. Actual Numerical Results

| Metric | Low Demand | Expected Demand | High Demand |
|---|---|---|---|
| Forecast demand | 5,727.6 | 6,385.1 | 7,042.5 |
| Unmet before transfers | 869.3 | 1,119.7 | 1,426.8 |
| Unmet after transfers | 10.0 | 12.4 | 22.6 |
| Recommended transfers | 22 | 28 | 30 |
| Units transferred | 860 | 1,108 | 1,405 |
| Transfer cost (AED) | 1,569.50 | 2,021.50 | 2,559.50 |
| Margin preserved (AED) | 36,455.53 | 46,838.67 | 60,202.18 |
| Net benefit (AED) | 34,886.03 | 44,817.17 | 57,642.68 |

## D. Optimizer Produces Different Recommendations

**Yes — the optimizer produces different transfer recommendations for each scenario.**

| Scenario | Transfers | Units | Cost | Net Benefit |
|---|---|---|---|---|
| Low Demand | 22 | 860 | 1,569.50 | 34,886.03 |
| Expected Demand | 28 | 1,108 | 2,021.50 | 44,817.17 |
| High Demand | 30 | 1,405 | 2,559.50 | 57,642.68 |

The MILP solver is rerun for each scenario with modified daily demand inputs. The optimizer selects different transfers because different SKU-warehouse combinations fall into shortage under each demand scenario.

## E. Test Results

**All 29 tests passed, 0 failed.**

### Smoke Tests (15/15 passed)
| # | Test | Status |
|---|---|---|
| 1 | Data loading | PASS |
| 2 | Risk computation + 60 combo | PASS |
| 3 | MILP optimizer + economic constraint | PASS |
| 4 | What-If simulation | PASS |
| 5 | Disruption simulation | PASS |
| 6 | Ageing chart fix | PASS |
| 7 | Approval persistence + audit trail | PASS |
| 8 | Original datasets present | PASS |
| 9 | All page modules import | PASS |
| 10 | All agent classes import | PASS |
| 11 | AI assistant ageing label (regression) | PASS |
| 12 | AI assistant ageing alt spelling (regression) | PASS |
| 13 | Env var typo fix (regression) | PASS |
| 14 | Dead code removed (regression) | PASS |
| 15 | Optimizer works after cleanup (regression) | PASS |

### Demand Uncertainty Tests (14/14 passed)
| # | Test | Status |
|---|---|---|
| 1 | Low <= Expected <= High demand | PASS |
| 2 | No negative demand predictions | PASS |
| 3 | All three scenarios execute successfully | PASS |
| 4 | Expected-demand matches existing baseline | PASS |
| 5 | Inventory conservation maintained | PASS |
| 6 | Transfer quantities non-negative integers | PASS |
| 7 | Safety stock respected | PASS |
| 8 | Route constraints valid | PASS |
| 9 | Transfer costs recalculated correctly | PASS |
| 10 | Economic benefits recalculated correctly | PASS |
| 11 | Original datasets unchanged (MD5 hash) | PASS |
| 12 | Sealed answer key not accessed | PASS |
| 13 | Application loads new page | PASS |
| 14 | Optimizer produces different recommendations | PASS |

## F. Remaining Limitations

1. **i.i.d. assumption** — The uncertainty scaling (`sigma_daily * sqrt(30)`) assumes daily residuals are independent. Real demand errors exhibit autocorrelation, so true 30-day uncertainty is likely higher.
2. **Short test window** — Test residuals cover only 15 days (days 76-90). The 30-day forecast horizon is longer.
3. **Per-combo noise** — Only ~14-15 test points per SKU-warehouse combo, so we use global sigma rather than per-combo sigma.
4. **Not calibrated** — These are empirical sensitivity bounds, not statistically calibrated prediction intervals.
5. **No robust optimization** — The system runs separate optimizations per scenario. A genuine robust optimization would optimize across all scenarios simultaneously.

## G. Demonstration Instructions

1. **Run the app:** `streamlit run app.py`
2. **Navigate** to the **Demand Uncertainty** page (7th item in sidebar)
3. **Show the uncertainty method** — point out sigma_daily = 2.00, sigma_30d = 10.96, 875 test residuals
4. **Show the comparison table** — Low (22 transfers, 34,886 AED) vs Expected (28, 44,817 AED) vs High (30, 57,643 AED)
5. **Select "High Demand"** in the interactive scenario selector — show the different transfer recommendations
6. **Show the robust decision analysis** — explain that the expected plan is not robust to high demand
7. **Point out the explanation panel** — "AI forecasts are not guaranteed. These are empirical sensitivity bounds."
8. **Run tests:** `python smoke_test.py && python test_demand_uncertainty.py`
