"""Metric calculation helpers for TradeFlow AI dashboard."""

import pandas as pd
import numpy as np
from typing import Optional


def load_data(data_dir: str) -> dict:
    """Load all key datasets from the data directory."""
    import os
    data = {}
    file_map = {
        "products": "products.csv",
        "warehouses": "warehouses.csv",
        "sales": "sales_history.csv",
        "inventory": "inventory.csv",
        "scenario_inventory": "scenario_inventory.csv",
        "inventory_risks": "inventory_risks.csv",
        "scenario_risks": "scenario_inventory_risks.csv",
        "daily_forecast": "improved_daily_forecasts.csv",
        "forecast_30d": "improved_forecast_30d.csv",
        "scenario_projection": "scenario_daily_inventory_projection.csv",
        "transfer_routes": "transfer_routes.csv",
        "transfer_recs": "transfer_recommendations.csv",
        "post_transfer_proj": "post_transfer_inventory_projection.csv",
        "opt_summary": "transfer_optimization_summary.csv",
        "scenario_inbound": "scenario_inbound_orders.csv",
        "inbound": "inbound_orders.csv",
        "stock_ageing": "stock_ageing.csv",
        "scenario_ageing": "scenario_stock_ageing.csv",
        "disruptions": "disruptions.csv",
    }
    for key, fname in file_map.items():
        path = os.path.join(data_dir, fname)
        if os.path.exists(path):
            parse_dates = []
            if "Date" in ["Date"]:
                parse_dates = ["Date"]
            if fname in ("improved_daily_forecasts.csv", "sales_history.csv"):
                data[key] = pd.read_csv(path, parse_dates=["Date"])
            elif fname in ("scenario_inbound_orders.csv", "inbound_orders.csv"):
                data[key] = pd.read_csv(path, parse_dates=["Expected_Arrival"])
            else:
                data[key] = pd.read_csv(path)
        else:
            data[key] = None
    return data


def get_scenario_inventory(data: dict, scenario: str) -> pd.DataFrame:
    """Get inventory for the selected scenario."""
    if scenario == "demonstration":
        return data["scenario_inventory"].copy()
    return data["inventory"].copy()


def get_scenario_risks(data: dict, scenario: str) -> pd.DataFrame:
    """Get risk data for the selected scenario."""
    if scenario == "demonstration":
        return data["scenario_risks"].copy()
    return data["inventory_risks"].copy()


def get_scenario_inbound(data: dict, scenario: str) -> pd.DataFrame:
    """Get inbound orders for the selected scenario."""
    if scenario == "demonstration":
        return data["scenario_inbound"].copy()
    return data["inbound"].copy()


def get_scenario_ageing(data: dict, scenario: str) -> pd.DataFrame:
    """Get stock ageing for the selected scenario."""
    if scenario == "demonstration":
        return data["scenario_ageing"].copy()
    return data["stock_ageing"].copy()


def compute_risk_summary(inv_df: pd.DataFrame, forecast_30d: pd.DataFrame) -> dict:
    """Compute risk summary from inventory + forecast."""
    merged = inv_df.merge(
        forecast_30d[["SKU", "Warehouse", "Forecast_30d"]],
        on=["SKU", "Warehouse"], how="left",
    )
    merged["Unmet_Demand"] = (merged["Forecast_30d"] - merged["Available_Stock"]).clip(lower=0)
    merged["Excess_Stock"] = (merged["Available_Stock"] - merged["Forecast_30d"] - merged["Safety_Stock"]).clip(lower=0)

    def classify(row):
        if row["Unmet_Demand"] > 0:
            return "Critical"
        elif row["Available_Stock"] < row["Safety_Stock"]:
            return "Warning"
        elif row["Excess_Stock"] > 100:
            return "Excess"
        return "Healthy"

    merged["Risk_Class"] = merged.apply(classify, axis=1)

    risk_counts = merged["Risk_Class"].value_counts().to_dict()
    total_unmet = float(merged["Unmet_Demand"].sum())
    total_excess = float(merged["Excess_Stock"].sum())
    total_available = int(merged["Available_Stock"].sum())
    total_forecast = float(merged["Forecast_30d"].sum())
    coverage = total_available / total_forecast if total_forecast > 0 else 0

    # Economic exposure = unmet * margin
    if "products" in dir() or True:
        pass  # margin applied by caller

    by_warehouse = {}
    for wh in merged["Warehouse"].unique():
        wd = merged[merged["Warehouse"] == wh]
        by_warehouse[wh] = {
            "critical": int((wd["Risk_Class"] == "Critical").sum()),
            "warning": int((wd["Risk_Class"] == "Warning").sum()),
            "excess": int((wd["Risk_Class"] == "Excess").sum()),
            "healthy": int((wd["Risk_Class"] == "Healthy").sum()),
            "total_unmet": float(wd["Unmet_Demand"].sum()),
            "total_excess": float(wd["Excess_Stock"].sum()),
            "total_available": int(wd["Available_Stock"].sum()),
        }

    return {
        "risk_counts": risk_counts,
        "total_unmet": total_unmet,
        "total_excess": total_excess,
        "total_available": total_available,
        "total_forecast": total_forecast,
        "coverage_ratio": coverage,
        "by_warehouse": by_warehouse,
        "detailed": merged,
    }


def compute_economic_exposure(inv_df: pd.DataFrame, forecast_30d: pd.DataFrame,
                               products: pd.DataFrame) -> float:
    """Compute total economic exposure from unmet demand."""
    merged = inv_df.merge(
        forecast_30d[["SKU", "Warehouse", "Forecast_30d"]],
        on=["SKU", "Warehouse"], how="left",
    )
    merged["Unmet_Demand"] = (merged["Forecast_30d"] - merged["Available_Stock"]).clip(lower=0)
    margin_map = products.set_index("SKU")["Profit_Margin_AED"].to_dict()
    merged["Margin"] = merged["SKU"].map(margin_map).fillna(0)
    merged["Economic_Exposure"] = merged["Unmet_Demand"] * merged["Margin"]
    return float(merged["Economic_Exposure"].sum())


def get_opt_summary(data: dict) -> dict:
    """Parse optimization summary CSV into a dict."""
    df = data.get("opt_summary")
    if df is None:
        return {}
    result = {}
    for _, row in df.iterrows():
        result[row["Metric"]] = row["Value"]
    return result


def get_transfer_recs_df(data: dict) -> pd.DataFrame:
    """Get transfer recommendations as DataFrame."""
    df = data.get("transfer_recs")
    if df is None:
        return pd.DataFrame()
    return df.copy()


def compute_approved_plan_impact(orchestrator, scenario: str, all_recs: list) -> dict:
    """Calculate the impact of only approved transfers.

    Returns projected benefit from approved transfers only,
    distinct from the full proposed optimization benefit.

    **Two benefit metrics are returned:**

    1. ``approved_benefit`` / ``total_proposed_benefit`` — Sum of individual
       ``estimated_net_benefit_aed`` values per transfer. This is a simple
       arithmetic sum that does NOT account for interaction effects between
       transfers (e.g., two transfers arriving at the same destination on the
       same day share the same reducible unmet demand pool).

    2. ``optimizer_net_economic_benefit`` — The MILP optimizer's simulated
       net economic benefit, computed from the post-transfer daily inventory
       simulation. This is the value shown on the Transfer Optimization page
       (~44,817 AED). It accounts for actual demand fulfillment dynamics,
       including lead-time effects and inbound order arrivals.

    The percentage displayed on the Approval Center uses the sum-of-individual
    benefit as the denominator (metric 1), NOT the optimizer's simulated
    benefit (metric 2). This is clearly labeled to avoid confusion.
    """
    approved_recs = [r for r in all_recs if r.get("approval_status") == "Approved"]
    pending_recs = [r for r in all_recs if r.get("approval_status") == "Pending"]
    rejected_recs = [r for r in all_recs if r.get("approval_status") == "Rejected"]

    approved_benefit = sum(r.get("estimated_net_benefit_aed", 0) for r in approved_recs)
    pending_benefit = sum(r.get("estimated_net_benefit_aed", 0) for r in pending_recs)
    rejected_benefit = sum(r.get("estimated_net_benefit_aed", 0) for r in rejected_recs)
    total_benefit = approved_benefit + pending_benefit + rejected_benefit

    approved_units = sum(r.get("transfer_quantity", 0) for r in approved_recs)
    approved_cost = sum(r.get("transfer_cost_aed", 0) for r in approved_recs)
    approved_unmet_avoided = sum(r.get("expected_unmet_avoided", 0) for r in approved_recs)

    # Retrieve the optimizer's simulated net economic benefit for context.
    # This is the value shown on the Transfer Optimization page (~44,817 AED).
    optimizer_net_benefit = 0.0
    optimizer_total_cost = 0.0
    optimizer_margin_preserved = 0.0
    try:
        opt_result = orchestrator.get_transfer_recommendations(scenario)
        optimizer_net_benefit = float(opt_result.get("net_economic_benefit", 0.0))
        optimizer_total_cost = float(opt_result.get("total_transfer_cost", 0.0))
        optimizer_margin_preserved = float(
            opt_result.get("actual_margin_preserved",
                           opt_result.get("margin_preserved", 0.0))
        )
    except Exception:
        pass  # Orchestrator may not be available in all contexts

    return {
        "approved_count": len(approved_recs),
        "pending_count": len(pending_recs),
        "rejected_count": len(rejected_recs),
        "total_count": len(all_recs),
        "approved_benefit": approved_benefit,
        "pending_benefit": pending_benefit,
        "rejected_benefit": rejected_benefit,
        "total_proposed_benefit": total_benefit,
        "approved_units": approved_units,
        "approved_cost": approved_cost,
        "approved_unmet_avoided": approved_unmet_avoided,
        "approved_recs": approved_recs,
        "pending_recs": pending_recs,
        "rejected_recs": rejected_recs,
        # Optimizer's simulated values (from post-transfer daily simulation)
        "optimizer_net_economic_benefit": optimizer_net_benefit,
        "optimizer_total_transfer_cost": optimizer_total_cost,
        "optimizer_margin_preserved": optimizer_margin_preserved,
    }


def generate_ai_insights(inv_df: pd.DataFrame, forecast_30d: pd.DataFrame,
                          products: pd.DataFrame, opt_summary: dict,
                          scenario: str) -> list:
    """Generate automated AI insights from actual data."""
    insights = []
    merged = inv_df.merge(
        forecast_30d[["SKU", "Warehouse", "Forecast_30d"]],
        on=["SKU", "Warehouse"], how="left",
    )
    merged["Unmet_Demand"] = (merged["Forecast_30d"] - merged["Available_Stock"]).clip(lower=0)
    merged["Excess_Stock"] = (merged["Available_Stock"] - merged["Forecast_30d"] - merged["Safety_Stock"]).clip(lower=0)
    margin_map = products.set_index("SKU")["Profit_Margin_AED"].to_dict()
    merged["Margin"] = merged["SKU"].map(margin_map).fillna(0)

    # Highest shortage risk warehouse
    wh_unmet = merged.groupby("Warehouse")["Unmet_Demand"].sum()
    if wh_unmet.max() > 0:
        wh = wh_unmet.idxmax()
        insights.append({
            "icon": "warning",
            "title": "Highest Shortage Risk",
            "text": f"{wh} has the highest projected unmet demand ({wh_unmet[wh]:.0f} units).",
            "color": "red",
        })

    # Highest excess warehouse
    wh_excess = merged.groupby("Warehouse")["Excess_Stock"].sum()
    if wh_excess.max() > 0:
        wh = wh_excess.idxmax()
        insights.append({
            "icon": "info",
            "title": "Most Excess Inventory",
            "text": f"{wh} has the most excess stock ({wh_excess[wh]:.0f} units above forecast + safety).",
            "color": "purple",
        })

    # Most valuable transfer — only for demonstration scenario (has shortages)
    if scenario == "demonstration" and opt_summary and "Net economic benefit" in opt_summary:
        net = opt_summary["Net economic benefit"]
        num_recs = opt_summary.get("Number of recommended transfers", 0)
        insights.append({
            "icon": "money",
            "title": "Projected Economic Benefit",
            "text": f"{int(num_recs)} recommended transfers project {net:,.0f} AED net economic benefit.",
            "color": "blue",
        })
    elif scenario == "original":
        # For original scenario: no shortage-driven transfers, focus on excess
        total_excess_val = float(merged["Excess_Stock"].sum())
        if total_excess_val > 0:
            # Estimate potential storage savings (illustrative)
            insights.append({
                "icon": "info",
                "title": "Excess Inventory Opportunity",
                "text": f"{total_excess_val:,.0f} units of excess stock could be redistributed or consolidated to reduce holding costs.",
                "color": "purple",
            })

    # Total critical combos
    critical = (merged["Unmet_Demand"] > 0).sum()
    if critical > 0:
        total_unmet = merged["Unmet_Demand"].sum()
        total_exposure = (merged["Unmet_Demand"] * merged["Margin"]).sum()
        insights.append({
            "icon": "alert",
            "title": "Critical Shortages",
            "text": f"{critical} SKU-warehouse combinations face shortages totaling {total_unmet:.0f} units ({total_exposure:,.0f} AED exposure).",
            "color": "red",
        })

    # Coverage ratio
    total_avail = merged["Available_Stock"].sum()
    total_fc = merged["Forecast_30d"].sum()
    ratio = total_avail / total_fc if total_fc > 0 else 0
    insights.append({
        "icon": "chart",
        "title": "Coverage Ratio",
        "text": f"System-wide inventory covers {ratio:.1f}x the 30-day forecast demand.",
        "color": "teal",
    })

    return insights
