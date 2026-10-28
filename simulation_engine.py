"""What-If & Disruption Simulation Engine.

Runs actual backend recalculations (risk + MILP optimization) on a modified
inventory copy — never touching the original CSV files.

Functions:
    run_whatif_simulation(data_dir, scenario, sku, warehouse, new_available, new_safety)
    run_disruption_simulation(data_dir, scenario, disruption_type)
"""

import os
import copy
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Reuse the existing optimizer's simulation logic by subclassing
from tradeflow_agents.optimization_agent import OptimizationAgent
from components.metrics import compute_risk_summary, compute_economic_exposure


class _SimulationOptimizer(OptimizationAgent):
    """Subclass of OptimizationAgent that accepts a custom inventory DataFrame.

    This allows the What-If simulator to rerun the exact same MILP pipeline
    on a modified inventory without writing any CSV files.
    """

    def __init__(self, data_dir: str, modified_inventory: pd.DataFrame,
                 modified_inbound: pd.DataFrame = None):
        # Temporarily write nothing — we'll override after parent init
        # But parent __init__ reads CSVs from disk. We'll let it do that,
        # then override the scenario_inventory with our modified copy.
        super().__init__(data_dir)

        # Override scenario inventory with the modified copy
        self._custom_inventory = modified_inventory.copy()

        # Optionally override inbound orders (for disruption simulation)
        if modified_inbound is not None:
            self._custom_inbound = modified_inbound.copy()
        else:
            self._custom_inbound = None

        # Rebuild lookups that depend on inventory
        self.wh_list = sorted(modified_inventory["Warehouse"].unique())
        self.sku_list = sorted(modified_inventory["SKU"].unique())

    def _get_inventory(self, scenario: str) -> pd.DataFrame:
        """Always return the modified inventory regardless of scenario."""
        return self._custom_inventory.copy()

    def _get_inbound(self, scenario: str) -> pd.DataFrame:
        """Return modified inbound if set, else fall back to scenario inbound."""
        if self._custom_inbound is not None:
            return self._custom_inbound.copy()
        return super()._get_inbound(scenario)


def run_whatif_simulation(
    data_dir: str,
    scenario: str,
    sku: str,
    warehouse: str,
    new_available: int,
    new_safety: int = None,
) -> dict:
    """Run a full what-if simulation with modified inventory for one SKU-warehouse combo.

    Steps:
        1. Load the scenario inventory into a working copy.
        2. Modify the selected SKU-warehouse combo.
        3. Recalculate inventory risk (shortage, excess, classification).
        4. Rerun the MILP transfer optimizer on the modified inventory.
        5. Return before-vs-after comparison.

    The original CSV files are never modified.

    Returns dict with:
        - baseline_risk: risk summary before the change
        - modified_risk: risk summary after the change
        - baseline_opt: optimization result before the change
        - modified_opt: optimization result after the change
        - changed_combo: the SKU-warehouse combo that was modified
        - forecast_note: explanation about forecast reuse
    """
    # Load original inventory for this scenario
    if scenario == "demonstration":
        inv_path = os.path.join(data_dir, "scenario_inventory.csv")
    else:
        inv_path = os.path.join(data_dir, "inventory.csv")

    original_inv = pd.read_csv(inv_path)

    # Create working copy
    modified_inv = original_inv.copy()

    # Find and modify the target combo
    mask = (modified_inv["SKU"] == sku) & (modified_inv["Warehouse"] == warehouse)
    if not mask.any():
        return {"error": f"SKU {sku} / Warehouse {warehouse} not found in inventory."}

    old_available = int(modified_inv.loc[mask, "Available_Stock"].values[0])
    old_safety = int(modified_inv.loc[mask, "Safety_Stock"].values[0])

    modified_inv.loc[mask, "Available_Stock"] = int(new_available)
    if new_safety is not None:
        modified_inv.loc[mask, "Safety_Stock"] = int(new_safety)
    else:
        new_safety = old_safety

    # Load forecast (unchanged — reused as-is)
    forecast_30d = pd.read_csv(os.path.join(data_dir, "improved_forecast_30d.csv"))
    products = pd.read_csv(os.path.join(data_dir, "products.csv"))

    # ── Baseline risk (before change) ──
    baseline_risk = compute_risk_summary(original_inv, forecast_30d)
    baseline_exposure = compute_economic_exposure(original_inv, forecast_30d, products)

    # ── Modified risk (after change) ──
    modified_risk = compute_risk_summary(modified_inv, forecast_30d)
    modified_exposure = compute_economic_exposure(modified_inv, forecast_30d, products)

    # ── Baseline optimization (original inventory) ──
    baseline_opt_agent = OptimizationAgent(data_dir)
    try:
        baseline_opt = baseline_opt_agent.get_transfer_recommendations(scenario)
    except Exception as e:
        baseline_opt = {"error": str(e), "has_recommendations": False}
    finally:
        pass

    # ── Modified optimization (with changed inventory) ──
    # Use the simulation subclass with the modified inventory
    sim_agent = _SimulationOptimizer(data_dir, modified_inv)
    try:
        # Force "demonstration" scenario since we override _get_inventory
        modified_opt = sim_agent.get_transfer_recommendations(scenario)
    except Exception as e:
        modified_opt = {"error": str(e), "has_recommendations": False}

    # ── Check if modified combo has a shortage but no transfer recommended ──
    no_transfer_explanation = None
    modified_recs = modified_opt.get("recommendations", []) if isinstance(modified_opt, dict) and "error" not in modified_opt else []
    has_transfer_for_combo = any(
        r.get("sku") == sku and r.get("destination_warehouse") == warehouse
        for r in modified_recs
    )
    if not has_transfer_for_combo:
        try:
            no_transfer_explanation = explain_no_transfer_for_combo(
                data_dir, scenario, sku, warehouse, modified_inv,
            )
        except Exception:
            no_transfer_explanation = None

    return {
        "scenario": scenario,
        "changed_combo": {
            "sku": sku,
            "warehouse": warehouse,
            "old_available": old_available,
            "new_available": int(new_available),
            "old_safety": old_safety,
            "new_safety": int(new_safety),
        },
        "baseline_risk": {
            "total_unmet": baseline_risk["total_unmet"],
            "total_excess": baseline_risk["total_excess"],
            "risk_counts": baseline_risk["risk_counts"],
            "economic_exposure": baseline_exposure,
        },
        "modified_risk": {
            "total_unmet": modified_risk["total_unmet"],
            "total_excess": modified_risk["total_excess"],
            "risk_counts": modified_risk["risk_counts"],
            "economic_exposure": modified_exposure,
        },
        "baseline_opt": _extract_opt_summary(baseline_opt),
        "modified_opt": _extract_opt_summary(modified_opt),
        "transfer_diff": compare_transfer_recommendations(
            baseline_opt.get("recommendations", []) if isinstance(baseline_opt, dict) and "error" not in baseline_opt else [],
            modified_opt.get("recommendations", []) if isinstance(modified_opt, dict) and "error" not in modified_opt else [],
            sku, warehouse,
        ),
        "no_transfer_explanation": no_transfer_explanation,
        "forecast_note": (
            "The 30-day demand forecast was NOT regenerated. The existing XGBoost "
            "forecast (improved_forecast_30d.csv) was reused unchanged. Only inventory "
            "levels, risk classification, and MILP transfer optimization were recalculated."
        ),
        "simulation_note": "Interactive simulation — no physical inventory changes.",
        "original_files_preserved": True,
    }


def run_disruption_simulation(
    data_dir: str,
    scenario: str,
    disruption_type: str,
) -> dict:
    """Run a supply-chain disruption simulation.

    Uses the actual disruptions.csv data:
        - D001: Component Shortage (affects SKU-001, SKU-002, SKU-003; 10-day delay)
        - D002: Shipping Route Delay (Dubai→Abu Dhabi route; 5-day delay)

    For a component shortage:
        - Delays inbound orders for affected SKUs by the recorded delay days.
        - Reruns inventory simulation and optimization.

    For a shipping route delay:
        - Increases lead time on the affected route.
        - Reruns optimization (transfers on the delayed route arrive later).

    Returns dict with disruption details, affected items, before/after comparison.
    """
    # Load disruptions
    disruptions_path = os.path.join(data_dir, "disruptions.csv")
    if not os.path.exists(disruptions_path):
        return {"error": "disruptions.csv not found."}

    disruptions_df = pd.read_csv(disruptions_path)

    # Find the selected disruption
    disruption_map = {
        "No Disruption": None,
        "Component Supply Shortage": "Component Shortage",
        "Shipping Route Delay": "Shipping Route Delay",
    }

    target_type = disruption_map.get(disruption_type)
    if target_type is None:
        # No disruption selected — return baseline
        return _no_disruption_baseline(data_dir, scenario)

    disruption_row = disruptions_df[disruptions_df["Type"] == target_type]
    if disruption_row.empty:
        return {"error": f"No disruption of type '{target_type}' found in disruptions.csv."}

    row = disruption_row.iloc[0]
    delay_days = int(row["Delay_Days"])
    affected_skus = row["Affected_SKUs"]
    affected_route = row["Affected_Route"]
    description = row["Description"]

    # ── Load scenario data ──
    if scenario == "demonstration":
        inv_path = os.path.join(data_dir, "scenario_inventory.csv")
        inbound_path = os.path.join(data_dir, "scenario_inbound_orders.csv")
    else:
        inv_path = os.path.join(data_dir, "inventory.csv")
        inbound_path = os.path.join(data_dir, "inbound_orders.csv")

    original_inv = pd.read_csv(inv_path)
    original_inbound = pd.read_csv(inbound_path, parse_dates=["Expected_Arrival"])
    forecast_30d = pd.read_csv(os.path.join(data_dir, "improved_forecast_30d.csv"))
    products = pd.read_csv(os.path.join(data_dir, "products.csv"))

    # ── Baseline (no disruption) ──
    baseline_risk = compute_risk_summary(original_inv, forecast_30d)
    baseline_exposure = compute_economic_exposure(original_inv, forecast_30d, products)

    baseline_opt_agent = OptimizationAgent(data_dir)
    try:
        baseline_opt = baseline_opt_agent.get_transfer_recommendations(scenario)
    except Exception as e:
        baseline_opt = {"error": str(e), "has_recommendations": False}

    if target_type == "Component Shortage":
        # ── Apply component shortage ──
        # Parse affected SKUs
        affected_sku_list = [s.strip() for s in str(affected_skus).split(",") if s.strip()]

        if not affected_sku_list:
            return {
                "error": "Component shortage disruption has no affected SKUs listed in disruptions.csv.",
                "disruption_id": row["Disruption_ID"],
            }

        # Delay inbound orders for affected SKUs by delay_days
        modified_inbound = original_inbound.copy()
        affected_mask = modified_inbound["SKU"].isin(affected_sku_list)
        affected_orders_count = int(affected_mask.sum())
        modified_inbound.loc[affected_mask, "Expected_Arrival"] = (
            modified_inbound.loc[affected_mask, "Expected_Arrival"]
            + pd.Timedelta(days=delay_days)
        )

        # Track which affected orders were pushed outside the 30-day horizon
        horizon_end = original_inbound["Expected_Arrival"].max()
        # Determine the simulation horizon (30 days from the earliest date)
        sim_start = original_inbound["Expected_Arrival"].min()
        sim_end = sim_start + pd.Timedelta(days=30)
        original_in_horizon = original_inbound[affected_mask &
            (original_inbound["Expected_Arrival"] <= sim_end)]
        modified_in_horizon = modified_inbound[affected_mask &
            (modified_inbound["Expected_Arrival"] <= sim_end)]
        orders_pushed_out = len(original_in_horizon) - len(modified_in_horizon)

        # Build verification data
        affected_orders_detail = []
        for idx in original_inbound[affected_mask].index:
            affected_orders_detail.append({
                "sku": original_inbound.loc[idx, "SKU"],
                "warehouse": original_inbound.loc[idx, "Warehouse"],
                "original_arrival": str(original_inbound.loc[idx, "Expected_Arrival"].date()),
                "disrupted_arrival": str(modified_inbound.loc[idx, "Expected_Arrival"].date()),
                "quantity": int(original_inbound.loc[idx, "Quantity"]),
            })

        # Run optimization with delayed inbound
        sim_agent = _SimulationOptimizer(data_dir, original_inv, modified_inbound)
        try:
            modified_opt = sim_agent.get_transfer_recommendations(scenario)
        except Exception as e:
            modified_opt = {"error": str(e), "has_recommendations": False}

        # Recalculate risk with delayed inbound (simulated projection changes)
        modified_risk = baseline_risk  # Risk summary is based on current stock, not projection
        modified_exposure = baseline_exposure

        affected_items = affected_sku_list
        affected_detail = (
            f"{affected_orders_count} inbound orders for SKUs {', '.join(affected_sku_list)} "
            f"delayed by {delay_days} days. "
            f"{orders_pushed_out} order(s) pushed outside the 30-day simulation window."
        )

    elif target_type == "Shipping Route Delay":
        # ── Apply shipping route delay ──
        if not affected_route or str(affected_route).strip() == "":
            return {
                "error": "Shipping delay disruption has no affected route listed in disruptions.csv.",
                "disruption_id": row["Disruption_ID"],
            }

        route_parts = str(affected_route).split("-")
        if len(route_parts) != 2:
            return {
                "error": f"Affected route '{affected_route}' is not in 'Origin-Destination' format.",
                "disruption_id": row["Disruption_ID"],
            }

        route_origin = route_parts[0].strip()
        route_dest = route_parts[1].strip()

        # Load transfer routes to find the affected one
        routes_path = os.path.join(data_dir, "transfer_routes.csv")
        routes_df = pd.read_csv(routes_path)
        route_mask = (routes_df["Origin"] == route_origin) & (routes_df["Destination"] == route_dest)
        if not route_mask.any():
            return {
                "error": f"Route '{affected_route}' not found in transfer_routes.csv.",
                "disruption_id": row["Disruption_ID"],
            }

        original_lead_time = int(routes_df.loc[route_mask, "Lead_Time_Days"].values[0])
        disrupted_lead_time = original_lead_time + delay_days

        # Create modified routes with increased lead time
        modified_routes = routes_df.copy()
        modified_routes.loc[route_mask, "Lead_Time_Days"] = disrupted_lead_time

        # We need to override the route_map in the optimizer
        # Use the simulation subclass with modified routes
        sim_agent = _SimulationOptimizer(data_dir, original_inv)

        # Override the route_map
        sim_agent.route_map = {}
        for _, r in modified_routes.iterrows():
            sim_agent.route_map[(r["Origin"], r["Destination"])] = {
                "cost": r["Cost_Per_Unit_AED"],
                "lead_time": int(r["Lead_Time_Days"]),
            }

        try:
            modified_opt = sim_agent.get_transfer_recommendations(scenario)
        except Exception as e:
            modified_opt = {"error": str(e), "has_recommendations": False}

        # Count transfers using the affected route in baseline recommendations
        baseline_recs = baseline_opt.get("recommendations", []) if isinstance(baseline_opt, dict) and "error" not in baseline_opt else []
        affected_transfers = [r for r in baseline_recs
                              if r.get("source_warehouse") == route_origin
                              and r.get("destination_warehouse") == route_dest]
        route_affected_orders_count = len(affected_transfers)

        # Build verification data
        route_verification = {
            "route": f"{route_origin} → {route_dest}",
            "original_lead_time": original_lead_time,
            "disrupted_lead_time": disrupted_lead_time,
            "transfers_using_route_in_baseline": len(affected_transfers),
            "transfer_details": [
                {
                    "sku": r.get("sku", ""),
                    "quantity": r.get("transfer_quantity", 0),
                    "original_arrival_day": f"day {original_lead_time}",
                    "disrupted_arrival_day": f"day {disrupted_lead_time}",
                }
                for r in affected_transfers
            ],
        }

        modified_risk = baseline_risk
        modified_exposure = baseline_exposure

        affected_items = [f"Route: {route_origin} → {route_dest}"]
        affected_detail = (
            f"Shipping route {route_origin} → {route_dest} lead time increased "
            f"from {original_lead_time} to {disrupted_lead_time} days (+{delay_days} delay)"
        )

    else:
        return {"error": f"Unknown disruption type: {target_type}"}

    # Determine affected_orders_count and verification_data based on disruption type
    if target_type == "Component Shortage":
        _affected_orders_count = affected_orders_count
        _verification_data = {
            "type": "component_shortage",
            "affected_skus": affected_sku_list,
            "delay_days": delay_days,
            "affected_orders": affected_orders_detail,
            "orders_pushed_outside_horizon": orders_pushed_out,
        }
    elif target_type == "Shipping Route Delay":
        _affected_orders_count = route_affected_orders_count
        _verification_data = route_verification
    else:
        _affected_orders_count = "N/A"
        _verification_data = {}

    return {
        "scenario": scenario,
        "disruption_type": disruption_type,
        "disruption_id": row["Disruption_ID"],
        "description": description,
        "delay_days": delay_days,
        "affected_items": affected_items,
        "affected_detail": affected_detail,
        "affected_orders_count": _affected_orders_count,
        "verification_data": _verification_data,
        "baseline_risk": {
            "total_unmet": baseline_risk["total_unmet"],
            "total_excess": baseline_risk["total_excess"],
            "risk_counts": baseline_risk["risk_counts"],
            "economic_exposure": baseline_exposure,
        },
        "modified_risk": {
            "total_unmet": modified_risk["total_unmet"],
            "total_excess": modified_risk["total_excess"],
            "risk_counts": modified_risk["risk_counts"],
            "economic_exposure": modified_exposure,
        },
        "baseline_opt": _extract_opt_summary(baseline_opt),
        "modified_opt": _extract_opt_summary(modified_opt),
        "forecast_note": (
            "The 30-day demand forecast was NOT regenerated. The existing XGBoost "
            "forecast was reused unchanged. Only inbound delivery timing and/or "
            "transfer lead times were modified per the disruption record."
        ),
        "simulation_note": "Interactive simulation — no physical inventory changes.",
        "original_files_preserved": True,
    }


def _no_disruption_baseline(data_dir: str, scenario: str) -> dict:
    """Return baseline results with no disruption applied."""
    if scenario == "demonstration":
        inv_path = os.path.join(data_dir, "scenario_inventory.csv")
    else:
        inv_path = os.path.join(data_dir, "inventory.csv")

    inv = pd.read_csv(inv_path)
    forecast_30d = pd.read_csv(os.path.join(data_dir, "improved_forecast_30d.csv"))
    products = pd.read_csv(os.path.join(data_dir, "products.csv"))

    risk = compute_risk_summary(inv, forecast_30d)
    exposure = compute_economic_exposure(inv, forecast_30d, products)

    opt_agent = OptimizationAgent(data_dir)
    try:
        opt = opt_agent.get_transfer_recommendations(scenario)
    except Exception as e:
        opt = {"error": str(e), "has_recommendations": False}

    return {
        "scenario": scenario,
        "disruption_type": "No Disruption",
        "disruption_id": None,
        "description": "No supply chain disruption applied.",
        "delay_days": 0,
        "affected_items": [],
        "affected_detail": "No disruption — baseline scenario.",
        "affected_orders_count": 0,
        "verification_data": {},
        "baseline_risk": {
            "total_unmet": risk["total_unmet"],
            "total_excess": risk["total_excess"],
            "risk_counts": risk["risk_counts"],
            "economic_exposure": exposure,
        },
        "modified_risk": {
            "total_unmet": risk["total_unmet"],
            "total_excess": risk["total_excess"],
            "risk_counts": risk["risk_counts"],
            "economic_exposure": exposure,
        },
        "baseline_opt": _extract_opt_summary(opt),
        "modified_opt": _extract_opt_summary(opt),
        "forecast_note": "No disruption — forecast and optimization unchanged.",
        "simulation_note": "Interactive simulation — no physical inventory changes.",
        "original_files_preserved": True,
    }


def _extract_opt_summary(opt_result: dict) -> dict:
    """Extract key optimization metrics for comparison."""
    if not opt_result or "error" in opt_result:
        return {
            "has_recommendations": False,
            "num_recommendations": 0,
            "total_units": 0,
            "transfer_cost": 0.0,
            "baseline_unmet": 0.0,
            "post_transfer_unmet": 0.0,
            "unmet_avoided": 0.0,
            "net_economic_benefit": 0.0,
            "error": opt_result.get("error", "") if opt_result else "",
        }
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


def compare_transfer_recommendations(
    baseline_recs: list,
    modified_recs: list,
    changed_sku: str = None,
    changed_warehouse: str = None,
) -> dict:
    """Compare two sets of transfer recommendations from the optimizer.

    Groups recommendations by (SKU, source_warehouse, destination_warehouse)
    and returns added, removed, changed, unchanged lists.

    Each transfer dict from the optimizer contains:
        sku, source_warehouse, destination_warehouse, transfer_quantity,
        transfer_cost_aed, expected_unmet_avoided, estimated_net_benefit_aed,
        product_name, lead_time_days, arrival_date, etc.

    Returns:
        dict with keys:
            - added: transfers in modified but not baseline
            - removed: transfers in baseline but not modified
            - changed: transfers in both but with different quantity
            - unchanged: transfers in both with same quantity
            - modified_combo_recs: transfers involving changed_sku or changed_warehouse
            - summary: dict of counts
    """
    def _key(r):
        return (r.get("sku", ""), r.get("source_warehouse", ""), r.get("destination_warehouse", ""))

    baseline_map = {}
    for r in (baseline_recs or []):
        baseline_map[_key(r)] = r

    modified_map = {}
    for r in (modified_recs or []):
        modified_map[_key(r)] = r

    all_keys = set(baseline_map.keys()) | set(modified_map.keys())

    added = []
    removed = []
    changed = []
    unchanged = []
    modified_combo_recs = []

    for key in all_keys:
        b = baseline_map.get(key)
        m = modified_map.get(key)

        if b is None and m is not None:
            added.append(m)
        elif b is not None and m is None:
            removed.append(b)
        elif b is not None and m is not None:
            b_qty = b.get("transfer_quantity", 0)
            m_qty = m.get("transfer_quantity", 0)
            if b_qty != m_qty:
                changed.append({"baseline": b, "modified": m})
            else:
                unchanged.append(m)

        # Check if this transfer involves the modified SKU or warehouse
        if changed_sku or changed_warehouse:
            rec = m if m is not None else b
            sku = rec.get("sku", "")
            src = rec.get("source_warehouse", "")
            dst = rec.get("destination_warehouse", "")
            if (changed_sku and sku == changed_sku) or \
               (changed_warehouse and (src == changed_warehouse or dst == changed_warehouse)):
                entry = m if m is not None else b
                entry["change_type"] = ("added" if m and not b
                                        else "removed" if b and not m
                                        else "changed" if b.get("transfer_quantity", 0) != m.get("transfer_quantity", 0)
                                        else "unchanged")
                modified_combo_recs.append(entry)

    # Sort all lists by net benefit descending (most important first)
    def _sort_key(r):
        return -(r.get("estimated_net_benefit_aed", 0) if isinstance(r, dict) and "estimated_net_benefit_aed" in r
                 else r.get("modified", {}).get("estimated_net_benefit_aed", 0) if isinstance(r, dict) and "modified" in r
                 else 0)

    added.sort(key=_sort_key)
    removed.sort(key=_sort_key)
    changed.sort(key=_sort_key)
    unchanged.sort(key=_sort_key)
    modified_combo_recs.sort(key=_sort_key)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "modified_combo_recs": modified_combo_recs,
        "summary": {
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
            "unchanged_count": len(unchanged),
            "total_baseline": len(baseline_recs or []),
            "total_modified": len(modified_recs or []),
        },
    }


def explain_no_transfer_for_combo(
    data_dir: str,
    scenario: str,
    sku: str,
    warehouse: str,
    modified_inv: pd.DataFrame = None,
) -> dict:
    """Explain why no transfer is recommended for a SKU-warehouse combo with shortage.

    Uses actual optimizer constraints and data — never guesses.
    Checks each reason the optimizer would skip a transfer:
      1. No shortage detected (unmet demand == 0)
      2. No surplus warehouses for this SKU
      3. No transfer routes from surplus to shortage warehouse
      4. Net benefit per unit <= 0 (transfer cost >= profit margin)
      5. No transferable stock (all sources at safety stock minimum)
      6. Shortage occurs before transfer arrival (lead time too long)

    Returns dict with:
        - has_shortage: bool
        - reasons: list of reason strings (empty if a transfer IS recommended)
        - details: dict with specific data values
    """
    if modified_inv is not None:
        agent = _SimulationOptimizer(data_dir, modified_inv)
    else:
        agent = OptimizationAgent(data_dir)

    available_map, safety_map, reserved_map, inbound_map = agent._build_maps_for_scenario(scenario)
    inv = agent._get_inventory(scenario)
    safety_map = inv.set_index(["SKU", "Warehouse"])["Safety_Stock"].to_dict()

    # 1. Run baseline simulation to check shortage
    baseline_daily, baseline_summary = agent._simulate_inventory(
        available_map, safety_map, inbound_map,
    )

    combo_key = (sku, warehouse)
    combo_result = baseline_summary["combo_results"].get(combo_key, {})
    unmet = combo_result.get("Total_Unmet_Demand", 0)

    if unmet <= 0:
        return {
            "has_shortage": False,
            "reasons": [f"No shortage detected for {sku} at {warehouse} — unmet demand is 0. No transfer needed."],
            "details": {"unmet_demand": unmet},
        }

    # 2. Check for surplus warehouses for this SKU
    shortage_combos = []
    surplus_combos = []
    for s in agent.sku_list:
        for w in agent.wh_list:
            r = baseline_summary["combo_results"][(s, w)]
            u = r["Total_Unmet_Demand"]
            ending = r["Ending_Stock"]
            safety = safety_map.get((s, w), 0)
            available = available_map.get((s, w), 0)
            fc30 = agent.forecast_30d_map.get((s, w), 0)
            if u > 0:
                shortage_combos.append({"SKU": s, "Warehouse": w, "Unmet_Demand": u,
                                        "Safety_Stock": safety, "Available_Stock": available,
                                        "Ending_Stock": ending})
            if ending > 2 * safety and ending > fc30 * 0.5:
                surplus_combos.append({"SKU": s, "Warehouse": w, "Ending_Stock": ending,
                                       "Safety_Stock": safety, "Available_Stock": available})

    sku_surpluses = [s for s in surplus_combos if s["SKU"] == sku and s["Warehouse"] != warehouse]

    if not sku_surpluses:
        return {
            "has_shortage": True,
            "reasons": [
                f"{sku} at {warehouse} has a shortage of {unmet:.0f} units, but no other warehouse "
                f"has surplus stock for {sku}. All other warehouses either also have shortages "
                f"or their ending stock is below the surplus threshold "
                f"(ending > 2 × safety stock AND > 50% of 30-day forecast)."
            ],
            "details": {
                "unmet_demand": unmet,
                "surplus_warehouses_for_sku": [],
                "all_warehouses_for_sku": [
                    {"warehouse": w, "ending_stock": baseline_summary["combo_results"][(sku, w)]["Ending_Stock"],
                     "unmet": baseline_summary["combo_results"][(sku, w)]["Total_Unmet_Demand"]}
                    for w in agent.wh_list
                ],
            },
        }

    # 3. Check for transfer routes from surplus to shortage warehouse
    routes_available = []
    routes_missing = []
    for s in sku_surpluses:
        src = s["Warehouse"]
        route_key = (src, warehouse)
        if route_key in agent.route_map:
            routes_available.append({
                "source": src, "destination": warehouse,
                "cost_per_unit": agent.route_map[route_key]["cost"],
                "lead_time_days": agent.route_map[route_key]["lead_time"],
            })
        else:
            routes_missing.append({"source": src, "destination": warehouse})

    if not routes_available:
        surplus_names = [s["Warehouse"] for s in sku_surpluses]
        return {
            "has_shortage": True,
            "reasons": [
                f"{sku} at {warehouse} has a shortage of {unmet:.0f} units, and surplus stock "
                f"exists at {', '.join(surplus_names)}. However, no transfer route is defined "
                f"from any surplus warehouse to {warehouse} in transfer_routes.csv."
            ],
            "details": {
                "unmet_demand": unmet,
                "surplus_warehouses": surplus_names,
                "missing_routes": routes_missing,
            },
        }

    # 4 & 5. Check net benefit and transferable stock
    margin = agent.margin_map.get(sku, 0)
    reasons = []
    details = {
        "unmet_demand": unmet,
        "profit_margin_aed": margin,
        "candidate_routes": [],
    }

    for s in sku_surpluses:
        src = s["Warehouse"]
        route_key = (src, warehouse)
        if route_key not in agent.route_map:
            continue
        cost_per_unit = agent.route_map[route_key]["cost"]
        lead_time = agent.route_map[route_key]["lead_time"]
        net_benefit_per_unit = margin - cost_per_unit

        # Check transferable stock
        available = available_map.get((sku, src), 0)
        fc_30d = agent.forecast_30d_map.get((sku, src), 0)
        safety = safety_map.get((sku, src), 0)
        transferable = max(0, int(np.floor(available - fc_30d - safety)))

        # Check if shortage is reducible (arrives before shortage)
        arrival_day = agent.horizon_start + timedelta(days=lead_time)
        sd_daily = baseline_daily[(baseline_daily["SKU"] == sku) &
                                   (baseline_daily["Warehouse"] == warehouse)].sort_values("Date")
        cum_unmet_by_day = {}
        running = 0.0
        for _, d in sd_daily.iterrows():
            running += d["Unmet_Demand"]
            cum_unmet_by_day[d["Date"]] = running

        cum_unmet_before_arrival = 0.0
        cum_unmet_total = 0.0
        for dt, cum in cum_unmet_by_day.items():
            cum_unmet_total = cum
            if dt < arrival_day:
                cum_unmet_before_arrival = cum

        reducible_unmet = max(0, cum_unmet_total - cum_unmet_before_arrival)

        route_detail = {
            "source": src,
            "destination": warehouse,
            "cost_per_unit_aed": cost_per_unit,
            "lead_time_days": lead_time,
            "net_benefit_per_unit_aed": net_benefit_per_unit,
            "transferable_stock": transferable,
            "reducible_unmet_demand": reducible_unmet,
            "available_stock_at_source": available,
            "forecast_30d_at_source": fc_30d,
            "safety_stock_at_source": safety,
        }
        details["candidate_routes"].append(route_detail)

        if net_benefit_per_unit <= 0:
            reasons.append(
                f"Route {src} → {warehouse}: transfer cost ({cost_per_unit:.2f} AED/unit) "
                f"≥ profit margin ({margin:.2f} AED/unit), so net benefit per unit is "
                f"{net_benefit_per_unit:.2f} AED. The optimizer only selects transfers with "
                f"positive net benefit."
            )
        elif transferable <= 0:
            reasons.append(
                f"Route {src} → {warehouse}: no transferable stock. Source has {available} units "
                f"available, but must keep {fc_30d:.0f} for its own 30-day forecast + "
                f"{safety} safety stock = {fc_30d + safety:.0f} reserved. "
                f"Transferable = {available} − {fc_30d + safety:.0f} = {transferable} units."
            )
        elif reducible_unmet <= 0:
            reasons.append(
                f"Route {src} → {warehouse}: transfer arrives on {arrival_day.strftime('%Y-%m-%d')} "
                f"(lead time {lead_time} days), but all {cum_unmet_total:.0f} units of shortage "
                f"occur before the transfer arrives. The optimizer cannot reduce shortages "
                f"that happen before the stock reaches the destination."
            )

    if not reasons:
        # A transfer should have been recommended — check if it actually is
        reasons.append(
            f"No blocking constraint found — a transfer for {sku} from a surplus warehouse "
            f"to {warehouse} should be feasible. Check if the MILP solver selected it."
        )

    return {
        "has_shortage": True,
        "reasons": reasons,
        "details": details,
    }
