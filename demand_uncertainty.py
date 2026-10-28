"""Demand Uncertainty Engine — Three-scenario demand analysis.

Generates Low / Expected / High demand scenarios from the XGBoost forecast
using empirical test-set residuals, then reruns the actual inventory risk
calculation and MILP transfer optimization for each scenario.

UNCERTAINTY METHOD
------------------
The XGBoost model was trained on a chronological split (train: days 1-60,
validation: days 61-75, test: days 76-90 of sales_history.csv). The file
``test_predictions.csv`` contains 875 out-of-sample predictions for the test
period with columns: Error (Actual - Predicted) and Abs_Error.

We use these test residuals to estimate forecast uncertainty:

    sigma_daily = std(Error)              # daily residual std (~2.00 units)
    sigma_30d   = sigma_daily * sqrt(30)  # scaled to 30-day horizon (~10.96 units)

This scaling assumes daily residuals are independent and identically
distributed (i.i.d.). This is a simplification — real demand errors exhibit
autocorrelation — but it provides a defensible, data-grounded estimate.

Three scenarios:
    - Low Demand:      Forecast_30d - sigma_30d  (per combo, floored at 0)
    - Expected Demand: Forecast_30d              (unchanged XGBoost forecast)
    - High Demand:     Forecast_30d + sigma_30d  (per combo)

For daily forecasts, each day's demand is scaled proportionally so that:
    sum(daily_low)  = Forecast_30d - sigma_30d
    sum(daily_high) = Forecast_30d + sigma_30d

All demand values are clipped to be non-negative.

LIMITATIONS
-----------
- The i.i.d. assumption likely understates true uncertainty for horizons
  where autocorrelation is positive.
- Test residuals cover a 15-day window (days 76-90); the 30-day forecast
  horizon is longer, so true uncertainty may be higher.
- Per-combo residual quantiles are noisy (only ~14-15 test points per combo),
  so we use the global sigma rather than per-combo sigma.
- These bounds are NOT statistically calibrated prediction intervals. They
  are empirical sensitivity bounds based on out-of-sample test residuals.
- The sealed future_demand_answer_key.csv is never accessed.

REUSES
------
- OptimizationAgent (subclassed to override demand_map)
- compute_risk_summary, compute_economic_exposure from components.metrics
"""

import os
import pandas as pd
import numpy as np
from datetime import timedelta

from tradeflow_agents.optimization_agent import OptimizationAgent
from components.metrics import (
    compute_risk_summary,
    compute_economic_exposure,
    get_scenario_inventory,
    get_scenario_risks,
)


# ──────────────────────────────────────────────────────────────
# Uncertainty estimation
# ──────────────────────────────────────────────────────────────

def load_test_residuals(data_dir: str) -> pd.DataFrame:
    """Load test_predictions.csv from the data directory.

    Returns DataFrame with columns:
        Date, SKU, Warehouse, Units_Sold, Predicted_Units_Sold, Error, Abs_Error

    Raises FileNotFoundError if the file does not exist.
    """
    path = os.path.join(data_dir, "test_predictions.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"test_predictions.csv not found at {path}. "
            "Cannot estimate forecast uncertainty without out-of-sample residuals."
        )
    df = pd.read_csv(path, parse_dates=["Date"])
    return df


def compute_uncertainty(data_dir: str) -> dict:
    """Compute demand forecast uncertainty from test residuals.

    Returns dict with:
        - sigma_daily: std of daily residuals (Error = Actual - Predicted)
        - sigma_30d: sigma_daily * sqrt(30) — 30-day horizon uncertainty
        - mae_daily: mean absolute error
        - n_residuals: number of test predictions
        - residual_quantiles: dict of quantile values
        - method_description: human-readable explanation
        - is_calibrated: False (empirical sensitivity, not calibrated interval)
    """
    residuals = load_test_residuals(data_dir)

    # Error = Actual - Predicted (positive means underforecast)
    errors = residuals["Error"].values
    abs_errors = residuals["Abs_Error"].values

    sigma_daily = float(np.std(errors, ddof=1))
    sigma_30d = sigma_daily * np.sqrt(30)
    mae_daily = float(np.mean(abs_errors))

    quantiles = {
        "q05": float(np.quantile(errors, 0.05)),
        "q10": float(np.quantile(errors, 0.10)),
        "q25": float(np.quantile(errors, 0.25)),
        "q50": float(np.quantile(errors, 0.50)),
        "q75": float(np.quantile(errors, 0.75)),
        "q90": float(np.quantile(errors, 0.90)),
        "q95": float(np.quantile(errors, 0.95)),
    }

    return {
        "sigma_daily": sigma_daily,
        "sigma_30d": sigma_30d,
        "mae_daily": mae_daily,
        "n_residuals": len(residuals),
        "residual_quantiles": quantiles,
        "method_description": (
            f"Uncertainty estimated from {len(residuals)} out-of-sample test predictions. "
            f"Daily residual std (sigma_daily) = {sigma_daily:.4f} units. "
            f"30-day horizon uncertainty (sigma_30d = sigma_daily * sqrt(30)) = {sigma_30d:.2f} units. "
            f"Method: empirical residual-based sensitivity analysis (NOT a statistically calibrated "
            f"prediction interval). Assumes i.i.d. daily residuals, which likely understates true "
            f"uncertainty due to demand autocorrelation."
        ),
        "is_calibrated": False,
    }


# ──────────────────────────────────────────────────────────────
# Demand scenario generation
# ──────────────────────────────────────────────────────────────

def generate_demand_scenarios(
    forecast_30d: pd.DataFrame,
    daily_forecast: pd.DataFrame,
    sigma_30d: float,
) -> dict:
    """Generate Low / Expected / High demand scenarios.

    Parameters
    ----------
    forecast_30d : DataFrame with columns SKU, Warehouse, Forecast_30d, Lower_Bound, Upper_Bound
    daily_forecast : DataFrame with columns Date, SKU, Warehouse, Predicted_Demand
    sigma_30d : float — 30-day horizon uncertainty (in units)

    Returns
    -------
    dict with keys "low", "expected", "high", each containing:
        - forecast_30d: DataFrame (SKU, Warehouse, Forecast_30d)
        - daily_forecast: DataFrame (Date, SKU, Warehouse, Predicted_Demand)
    """
    # Expected = unchanged
    exp_fc30 = forecast_30d.copy()
    exp_daily = daily_forecast.copy()

    # Low = Forecast_30d - sigma_30d (clipped to non-negative)
    low_fc30 = forecast_30d.copy()
    low_fc30["Forecast_30d"] = np.clip(low_fc30["Forecast_30d"] - sigma_30d, 0, None)

    # High = Forecast_30d + sigma_30d
    high_fc30 = forecast_30d.copy()
    high_fc30["Forecast_30d"] = high_fc30["Forecast_30d"] + sigma_30d

    # For daily forecasts, scale each day proportionally
    # so that sum(daily) matches the adjusted Forecast_30d
    def _adjust_daily(daily_df, fc30_adjusted):
        """Scale daily demand to match adjusted 30-day total per combo."""
        # Rename to avoid column collision on merge
        fc30_renamed = fc30_adjusted[["SKU", "Warehouse", "Forecast_30d"]].rename(
            columns={"Forecast_30d": "Target_30d"}
        )
        merged = daily_df.merge(fc30_renamed, on=["SKU", "Warehouse"])
        # Original 30-day sum per combo
        orig_sum = merged.groupby(["SKU", "Warehouse"])["Predicted_Demand"].transform("sum")
        # Scale factor = adjusted_total / original_total (guard against division by zero)
        scale = np.where(
            orig_sum > 0,
            merged["Target_30d"] / orig_sum,
            1.0,
        )
        merged["Predicted_Demand"] = np.clip(merged["Predicted_Demand"] * scale, 0, None)
        return merged[["Date", "SKU", "Warehouse", "Predicted_Demand"]]

    low_daily = _adjust_daily(daily_forecast, low_fc30)
    high_daily = _adjust_daily(daily_forecast, high_fc30)

    return {
        "low": {"forecast_30d": low_fc30, "daily_forecast": low_daily},
        "expected": {"forecast_30d": exp_fc30, "daily_forecast": exp_daily},
        "high": {"forecast_30d": high_fc30, "daily_forecast": high_daily},
    }


# ──────────────────────────────────────────────────────────────
# Demand-aware optimizer subclass
# ──────────────────────────────────────────────────────────────

class _DemandScenarioOptimizer(OptimizationAgent):
    """Subclass of OptimizationAgent that uses a modified demand_map.

    This allows rerunning the exact same MILP pipeline on modified demand
    inputs without writing any CSV files.
    """

    def __init__(self, data_dir: str, modified_daily_forecast: pd.DataFrame,
                 modified_forecast_30d: pd.DataFrame = None):
        super().__init__(data_dir)

        # Override the daily demand map
        self._custom_daily = modified_daily_forecast.copy()
        self._custom_fc30 = modified_forecast_30d.copy() if modified_forecast_30d is not None else None

        # Rebuild demand_map from modified daily forecast
        self.demand_map = {}
        for _, row in self._custom_daily.iterrows():
            self.demand_map[(row["SKU"], row["Warehouse"], row["Date"])] = row["Predicted_Demand"]

        # Override forecast_30d_map if provided
        if self._custom_fc30 is not None:
            self.forecast_30d_map = self._custom_fc30.set_index(["SKU", "Warehouse"])["Forecast_30d"].to_dict()


# ──────────────────────────────────────────────────────────────
# Full scenario analysis
# ──────────────────────────────────────────────────────────────

def _extract_opt_summary(opt_result: dict) -> dict:
    """Extract a normalized summary from optimization result."""
    return {
        "has_recommendations": opt_result.get("has_recommendations", False),
        "num_recommendations": opt_result.get("num_recommendations", 0),
        "total_units": opt_result.get("total_units_recommended", 0),
        "transfer_cost": opt_result.get("total_transfer_cost", 0.0),
        "baseline_unmet": opt_result.get("baseline_unmet", 0.0),
        "post_transfer_unmet": opt_result.get("post_transfer_unmet", 0.0),
        "unmet_avoided": opt_result.get("unmet_avoided", 0.0),
        "margin_preserved": opt_result.get("actual_margin_preserved", opt_result.get("margin_preserved", 0.0)),
        "net_economic_benefit": opt_result.get("net_economic_benefit", 0.0),
        "recommendations": opt_result.get("recommendations", []),
    }


def evaluate_plan_under_different_demand(
    plan_recs: list,
    target_daily_forecast: pd.DataFrame,
    target_forecast_30d: pd.DataFrame,
    data_dir: str,
    scenario: str,
) -> dict:
    """Evaluate an existing transfer plan against a different demand scenario.

    This is the core robustness check: take the transfers recommended for one
    demand scenario and simulate them against a different demand scenario's
    daily demand and inbound orders.

    Parameters
    ----------
    plan_recs : list of recommendation dicts (from optimization result)
    target_daily_forecast : DataFrame with the target scenario's daily demand
    target_forecast_30d : DataFrame with the target scenario's 30-day forecast
    data_dir : str — path to datasets directory
    scenario : str — "demonstration" or "original"

    Returns
    -------
    dict with:
        - post_transfer_unmet: float — unmet demand after applying plan_recs
        - baseline_unmet: float — unmet demand with no transfers (target demand)
        - unmet_avoided: float — baseline_unmet - post_transfer_unmet
        - num_transfers: int — number of transfers in the plan
        - total_units: int — total units transferred
    """
    # Build an optimizer with the TARGET demand scenario
    agent = _DemandScenarioOptimizer(data_dir, target_daily_forecast, target_forecast_30d)

    # Get the inventory and inbound for the scenario
    available_map, safety_map, reserved_map, inbound_map = agent._build_maps_for_scenario(scenario)
    inv = agent._get_inventory(scenario)
    safety_map = inv.set_index(["SKU", "Warehouse"])["Safety_Stock"].to_dict()

    # Baseline simulation (no transfers) under target demand
    _, baseline_summary = agent._simulate_inventory(
        available_map, safety_map, inbound_map,
    )

    # Convert plan_recs to simulation transfer format
    sim_transfers = []
    for r in plan_recs:
        sim_transfers.append({
            "SKU": r["sku"],
            "Source": r["source_warehouse"],
            "Destination": r["destination_warehouse"],
            "Quantity": r["transfer_quantity"],
            "Lead_Time_Days": r["lead_time_days"],
        })

    # Post-transfer simulation under target demand
    _, post_summary = agent._simulate_inventory(
        available_map, safety_map, inbound_map, transfers=sim_transfers,
    )

    baseline_unmet = baseline_summary["total_unmet"]
    post_unmet = post_summary["total_unmet"]

    return {
        "post_transfer_unmet": float(post_unmet),
        "baseline_unmet": float(baseline_unmet),
        "unmet_avoided": float(baseline_unmet - post_unmet),
        "num_transfers": len(plan_recs),
        "total_units": int(sum(r["transfer_quantity"] for r in plan_recs)),
    }


def run_demand_uncertainty_analysis(data_dir: str, scenario: str = "demonstration") -> dict:
    """Run full demand uncertainty analysis with three scenarios.

    For each scenario (low, expected, high):
        1. Generate modified demand forecasts.
        2. Run inventory risk calculation.
        3. Run daily inventory simulation + MILP optimization.
        4. Extract transfer recommendations and economic impact.

    Parameters
    ----------
    data_dir : str — path to the datasets directory
    scenario : str — "demonstration" or "original"

    Returns
    -------
    dict with keys:
        - uncertainty: dict from compute_uncertainty()
        - scenarios: dict with "low", "expected", "high" keys, each containing:
            - forecast_30d: DataFrame
            - daily_forecast: DataFrame
            - risk: dict from compute_risk_summary()
            - economic_exposure: float
            - optimization: dict from _extract_opt_summary()
        - comparison_table: list of dicts for the comparison table
        - method_note: str explaining the uncertainty method
    """
    # Load data
    from components.metrics import load_data
    data = load_data(data_dir)

    forecast_30d = data["forecast_30d"]
    daily_forecast = data["daily_forecast"]
    inv = get_scenario_inventory(data, scenario)

    # Compute uncertainty
    uncertainty = compute_uncertainty(data_dir)
    sigma_30d = uncertainty["sigma_30d"]

    # Generate demand scenarios
    scenarios = generate_demand_scenarios(forecast_30d, daily_forecast, sigma_30d)

    # Run analysis for each scenario
    results = {}
    for name, sc_data in scenarios.items():
        sc_fc30 = sc_data["forecast_30d"]
        sc_daily = sc_data["daily_forecast"]

        # 1. Inventory risk calculation (uses modified forecast_30d)
        risk = compute_risk_summary(inv, sc_fc30)

        # 2. Economic exposure
        products = data["products"]
        exposure = compute_economic_exposure(inv, sc_fc30, products)

        # 3. MILP optimization with modified demand
        opt_agent = _DemandScenarioOptimizer(data_dir, sc_daily, sc_fc30)
        opt_result = opt_agent.get_transfer_recommendations(scenario)
        opt_summary = _extract_opt_summary(opt_result)

        results[name] = {
            "forecast_30d": sc_fc30,
            "daily_forecast": sc_daily,
            "risk": risk,
            "economic_exposure": exposure,
            "optimization": opt_summary,
        }

    # Build comparison table
    comparison_table = []
    for name in ["low", "expected", "high"]:
        r = results[name]
        opt = r["optimization"]
        comparison_table.append({
            "Scenario": name.capitalize() + " Demand",
            "Forecast Demand": r["risk"]["total_forecast"],
            "Unmet Before Transfers": opt["baseline_unmet"],
            "Unmet After Transfers": opt["post_transfer_unmet"],
            "Recommended Transfers": opt["num_recommendations"],
            "Units Transferred": opt["total_units"],
            "Transfer Cost (AED)": opt["transfer_cost"],
            "Net Benefit (AED)": opt["net_economic_benefit"],
        })

    # ── Cross-scenario robustness evaluation ──
    # Evaluate the expected-demand transfer plan against high-demand inputs.
    # This answers: "If we execute the expected-demand plan but demand turns
    # out to be high, what is the post-transfer unmet demand?"
    exp_recs = results["expected"]["optimization"]["recommendations"]
    high_daily = results["high"]["daily_forecast"]
    high_fc30 = results["high"]["forecast_30d"]

    exp_plan_under_high = evaluate_plan_under_different_demand(
        exp_recs, high_daily, high_fc30, data_dir, scenario,
    )

    # Also evaluate expected-demand plan under expected demand (for reference)
    exp_daily = results["expected"]["daily_forecast"]
    exp_fc30 = results["expected"]["forecast_30d"]
    exp_plan_under_expected = evaluate_plan_under_different_demand(
        exp_recs, exp_daily, exp_fc30, data_dir, scenario,
    )

    robustness = {
        "exp_plan_under_exp_unmet": exp_plan_under_expected["post_transfer_unmet"],
        "exp_plan_under_high_unmet": exp_plan_under_high["post_transfer_unmet"],
        "high_plan_under_high_unmet": results["high"]["optimization"]["post_transfer_unmet"],
        "exp_plan_recs": results["expected"]["optimization"]["num_recommendations"],
        "high_plan_recs": results["high"]["optimization"]["num_recommendations"],
        "high_baseline_unmet": exp_plan_under_high["baseline_unmet"],
    }

    return {
        "uncertainty": uncertainty,
        "scenarios": results,
        "comparison_table": comparison_table,
        "robustness": robustness,
        "method_note": uncertainty["method_description"],
        "sigma_30d": sigma_30d,
        "scenario_name": scenario,
    }
