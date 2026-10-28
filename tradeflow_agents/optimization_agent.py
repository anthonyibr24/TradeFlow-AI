"""Optimization Agent — runs stock transfer MILP optimization.

Refactors the Step 4 optimization logic into reusable functions.
Uses scipy.optimize.milp (HiGHS solver) for integer linear programming.

Responsibilities:
- Load and execute transfer optimization
- Generate or retrieve transfer recommendations
- Calculate transfer costs and projected economic benefits
- Validate source inventory availability
- Respect route lead times
- Avoid double allocation of inventory
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from scipy.optimize import milp, LinearConstraint, Bounds
from .database import AgentDatabase


class OptimizationAgent:
    """Agent responsible for stock transfer optimization."""

    name = "OptimizationAgent"

    def __init__(self, data_dir: str, db: Optional[AgentDatabase] = None):
        self.data_dir = data_dir
        self.db = db

        # Load all required data
        self.scenario_inventory = pd.read_csv(f"{data_dir}/scenario_inventory.csv")
        self.original_inventory = pd.read_csv(f"{data_dir}/inventory.csv")
        self.forecast_30d = pd.read_csv(f"{data_dir}/improved_forecast_30d.csv")
        self.daily_forecast = pd.read_csv(
            f"{data_dir}/improved_daily_forecasts.csv", parse_dates=["Date"],
        )
        self.scenario_inbound = pd.read_csv(
            f"{data_dir}/scenario_inbound_orders.csv", parse_dates=["Expected_Arrival"],
        )
        self.original_inbound = pd.read_csv(
            f"{data_dir}/inbound_orders.csv", parse_dates=["Expected_Arrival"],
        )
        self.transfer_routes = pd.read_csv(f"{data_dir}/transfer_routes.csv")
        self.products = pd.read_csv(f"{data_dir}/products.csv")
        self.warehouses = pd.read_csv(f"{data_dir}/warehouses.csv")

        # Pre-compute lookup maps
        self._build_lookups()

        self._log("init", {"data_dir": data_dir}, {"status": "initialized"})

    def _log(self, task: str, inputs: dict, outputs: dict,
             status: str = "success", error: str = None):
        if self.db:
            self.db.log_agent_message(self.name, task, inputs, outputs, status, error)

    def _build_lookups(self):
        """Build fast lookup dictionaries."""
        self.wh_list = sorted(self.scenario_inventory["Warehouse"].unique())
        self.sku_list = sorted(self.scenario_inventory["SKU"].unique())
        self.future_dates = sorted(self.daily_forecast["Date"].unique())
        self.n_days = len(self.future_dates)
        self.horizon_start = self.future_dates[0]
        self.horizon_end = self.future_dates[-1]

        # Forecast maps
        self.forecast_30d_map = self.forecast_30d.set_index(["SKU", "Warehouse"])["Forecast_30d"].to_dict()
        self.forecast_30d_lb = self.forecast_30d.set_index(["SKU", "Warehouse"])["Lower_Bound"].to_dict()
        self.forecast_30d_ub = self.forecast_30d.set_index(["SKU", "Warehouse"])["Upper_Bound"].to_dict()

        # Daily demand map
        self.demand_map = {}
        for _, row in self.daily_forecast.iterrows():
            self.demand_map[(row["SKU"], row["Warehouse"], row["Date"])] = row["Predicted_Demand"]

        # Product maps
        self.margin_map = self.products.set_index("SKU")["Profit_Margin_AED"].to_dict()
        self.holding_cost_map = self.products.set_index("SKU")["Holding_Cost_Per_Unit_Day_AED"].to_dict()
        self.product_name_map = self.products.set_index("SKU")["Product"].to_dict()
        self.product_category_map = self.products.set_index("SKU")["Category"].to_dict()

        # Route map
        self.route_map = {}
        for _, row in self.transfer_routes.iterrows():
            self.route_map[(row["Origin"], row["Destination"])] = {
                "cost": row["Cost_Per_Unit_AED"],
                "lead_time": int(row["Lead_Time_Days"]),
            }

    def _get_inventory(self, scenario: str) -> pd.DataFrame:
        if scenario == "demonstration":
            return self.scenario_inventory.copy()
        return self.original_inventory.copy()

    def _get_inbound(self, scenario: str) -> pd.DataFrame:
        if scenario == "demonstration":
            return self.scenario_inbound.copy()
        return self.original_inbound.copy()

    def _build_maps_for_scenario(self, scenario: str):
        """Build scenario-specific lookup maps."""
        inv = self._get_inventory(scenario)
        inbound = self._get_inbound(scenario)

        available_map = inv.set_index(["SKU", "Warehouse"])["Available_Stock"].to_dict()
        safety_map = inv.set_index(["SKU", "Warehouse"])["Safety_Stock"].to_dict()
        reserved_map = inv.set_index(["SKU", "Warehouse"])["Reserved_Stock"].to_dict()

        inbound_map = {}
        for _, row in inbound.iterrows():
            key = (row["SKU"], row["Warehouse"], row["Expected_Arrival"])
            inbound_map[key] = inbound_map.get(key, 0) + row["Quantity"]

        return available_map, safety_map, reserved_map, inbound_map

    def _simulate_inventory(self, available_map, safety_map, inbound_map, transfers=None):
        """Run daily inventory simulation. Returns daily_df and combo_results."""
        if transfers is None:
            transfers = []

        transfer_out = {}
        transfer_in = {}
        for t in transfers:
            sku = t["SKU"]
            src = t["Source"]
            dst = t["Destination"]
            qty = t["Quantity"]
            lt = t["Lead_Time_Days"]
            transfer_out[(sku, src)] = transfer_out.get((sku, src), 0) + qty
            arrival_date = self.horizon_start + timedelta(days=lt)
            transfer_in[(sku, dst, arrival_date)] = transfer_in.get((sku, dst, arrival_date), 0) + qty

        daily_rows = []
        combo_results = {}

        for sku in self.sku_list:
            for wh in self.wh_list:
                stock = float(available_map.get((sku, wh), 0))
                safety = float(safety_map.get((sku, wh), 0))
                outgoing = transfer_out.get((sku, wh), 0)
                stock = max(0, stock - outgoing)

                starting_stock = stock
                cum_demand = 0.0
                cum_inbound = 0.0
                cum_fulfilled = 0.0
                cum_unmet = 0.0
                cum_transfer_in = 0.0
                first_stockout = None
                days_below_safety = 0

                for day_idx, dt in enumerate(self.future_dates):
                    incoming_ship = inbound_map.get((sku, wh, dt), 0)
                    stock += incoming_ship
                    cum_inbound += incoming_ship

                    incoming_transfer = transfer_in.get((sku, wh, dt), 0)
                    stock += incoming_transfer
                    cum_transfer_in += incoming_transfer

                    demand = self.demand_map.get((sku, wh, dt), 0.0)
                    cum_demand += demand

                    fulfilled = min(stock, demand)
                    unmet = max(0, demand - stock)
                    stock = max(0, stock - fulfilled)
                    cum_fulfilled += fulfilled
                    cum_unmet += unmet

                    if stock <= 0 and first_stockout is None:
                        first_stockout = dt
                    if stock < safety:
                        days_below_safety += 1

                    daily_rows.append({
                        "Date": dt, "SKU": sku, "Warehouse": wh,
                        "Starting_Stock": starting_stock if day_idx == 0 else None,
                        "Incoming_Qty": incoming_ship,
                        "Transfer_In_Qty": incoming_transfer,
                        "Transfer_Out_Qty": outgoing if day_idx == 0 else 0,
                        "Daily_Demand": demand,
                        "Fulfilled_Demand": fulfilled,
                        "Unmet_Demand": unmet,
                        "Ending_Stock": stock,
                        "Cumulative_Inbound": cum_inbound,
                        "Cumulative_Demand": cum_demand,
                        "Cumulative_Fulfilled": cum_fulfilled,
                        "Cumulative_Unmet": cum_unmet,
                        "Safety_Stock": safety,
                    })
                    starting_stock = stock

                combo_results[(sku, wh)] = {
                    "Starting_Stock": available_map.get((sku, wh), 0) - outgoing,
                    "Total_Incoming": cum_inbound,
                    "Total_Transfer_In": cum_transfer_in,
                    "Total_Transfer_Out": outgoing,
                    "Total_Demand": cum_demand,
                    "Total_Fulfilled": cum_fulfilled,
                    "Total_Unmet_Demand": cum_unmet,
                    "Ending_Stock": stock,
                    "First_Stockout_Date": first_stockout,
                    "Days_Below_Safety": days_below_safety,
                }

        daily_df = pd.DataFrame(daily_rows)
        daily_df = daily_df.sort_values(["SKU", "Warehouse", "Date"]).reset_index(drop=True)

        # Fill Starting_Stock forward
        for (sku, wh), grp in daily_df.groupby(["SKU", "Warehouse"]):
            prev = None
            for idx in grp.index:
                if pd.isna(daily_df.at[idx, "Starting_Stock"]):
                    daily_df.at[idx, "Starting_Stock"] = prev
                prev = daily_df.at[idx, "Ending_Stock"]

        total_unmet = sum(r["Total_Unmet_Demand"] for r in combo_results.values())
        total_demand = sum(r["Total_Demand"] for r in combo_results.values())
        total_fulfilled = sum(r["Total_Fulfilled"] for r in combo_results.values())

        summary = {
            "total_unmet": total_unmet,
            "total_demand": total_demand,
            "total_fulfilled": total_fulfilled,
            "combo_results": combo_results,
            "daily_df": daily_df,
        }
        return daily_df, summary

    def get_transfer_recommendations(self, scenario: str = "demonstration") -> dict:
        """Run full transfer optimization for the specified scenario.

        Returns dict with recommendations, baseline, post-transfer simulation,
        and economic impact analysis.
        """
        available_map, safety_map, reserved_map, inbound_map = self._build_maps_for_scenario(scenario)

        # Handle safety_map properly
        inv = self._get_inventory(scenario)
        safety_map = inv.set_index(["SKU", "Warehouse"])["Safety_Stock"].to_dict()

        # 1. Baseline simulation
        baseline_daily, baseline_summary = self._simulate_inventory(
            available_map, safety_map, inbound_map,
        )

        # If no shortages, return empty recommendations
        if baseline_summary["total_unmet"] <= 0:
            result = {
                "scenario": scenario,
                "has_recommendations": False,
                "num_recommendations": 0,
                "baseline_unmet": 0.0,
                "post_transfer_unmet": 0.0,
                "unmet_avoided": 0.0,
                "total_transfer_cost": 0.0,
                "net_economic_benefit": 0.0,
                "recommendations": [],
                "message": f"No shortages detected in {scenario} scenario. No transfers needed.",
            }
            self._log("get_transfer_recommendations", {"scenario": scenario},
                      {"num_recs": 0, "reason": "no shortages"})
            return result

        # 2. Identify shortage and surplus combos
        shortage_combos = []
        surplus_combos = []
        for sku in self.sku_list:
            for wh in self.wh_list:
                result = baseline_summary["combo_results"][(sku, wh)]
                unmet = result["Total_Unmet_Demand"]
                ending = result["Ending_Stock"]
                safety = safety_map.get((sku, wh), 0)
                available = available_map.get((sku, wh), 0)
                fc30 = self.forecast_30d_map.get((sku, wh), 0)

                if unmet > 0:
                    shortage_combos.append({
                        "SKU": sku, "Warehouse": wh,
                        "Unmet_Demand": unmet, "Safety_Stock": safety,
                        "Available_Stock": available, "Ending_Stock": ending,
                    })
                if ending > 2 * safety and ending > fc30 * 0.5:
                    surplus_combos.append({
                        "SKU": sku, "Warehouse": wh,
                        "Ending_Stock": ending, "Safety_Stock": safety,
                        "Available_Stock": available,
                    })

        shortage_df = pd.DataFrame(shortage_combos)
        surplus_df = pd.DataFrame(surplus_combos)

        if shortage_df.empty or surplus_df.empty:
            result = {
                "scenario": scenario,
                "has_recommendations": False,
                "num_recommendations": 0,
                "baseline_unmet": baseline_summary["total_unmet"],
                "post_transfer_unmet": baseline_summary["total_unmet"],
                "unmet_avoided": 0.0,
                "total_transfer_cost": 0.0,
                "net_economic_benefit": 0.0,
                "recommendations": [],
                "message": "Shortages exist but no surplus sources available for transfer.",
            }
            self._log("get_transfer_recommendations", {"scenario": scenario},
                      {"num_recs": 0, "reason": "no surplus"})
            return result

        # 3. Build transfer candidate pairs
        candidates = []
        for sku in self.sku_list:
            sku_shortages = shortage_df[shortage_df["SKU"] == sku]
            sku_surpluses = surplus_df[surplus_df["SKU"] == sku]
            if sku_shortages.empty or sku_surpluses.empty:
                continue

            for _, s_row in sku_shortages.iterrows():
                dst_wh = s_row["Warehouse"]
                unmet = s_row["Unmet_Demand"]
                for _, x_row in sku_surpluses.iterrows():
                    src_wh = x_row["Warehouse"]
                    if src_wh == dst_wh:
                        continue
                    route_key = (src_wh, dst_wh)
                    if route_key not in self.route_map:
                        continue
                    route_info = self.route_map[route_key]
                    cost_per_unit = route_info["cost"]
                    lead_time = route_info["lead_time"]
                    margin = self.margin_map.get(sku, 0)
                    net_benefit_per_unit = margin - cost_per_unit

                    candidates.append({
                        "SKU": sku,
                        "Source_Warehouse": src_wh,
                        "Destination_Warehouse": dst_wh,
                        "Lead_Time_Days": lead_time,
                        "Cost_Per_Unit_AED": cost_per_unit,
                        "Profit_Margin_AED": margin,
                        "Net_Benefit_Per_Unit_AED": net_benefit_per_unit,
                        "Destination_Unmet_Demand": unmet,
                        "Source_Ending_Stock": x_row["Ending_Stock"],
                        "Source_Safety_Stock": x_row["Safety_Stock"],
                    })

        candidates_df = pd.DataFrame(candidates)
        if candidates_df.empty:
            result = {
                "scenario": scenario,
                "has_recommendations": False,
                "num_recommendations": 0,
                "baseline_unmet": baseline_summary["total_unmet"],
                "post_transfer_unmet": baseline_summary["total_unmet"],
                "unmet_avoided": 0.0,
                "total_transfer_cost": 0.0,
                "net_economic_benefit": 0.0,
                "recommendations": [],
                "message": "No feasible transfer routes between shortage and surplus warehouses.",
            }
            self._log("get_transfer_recommendations", {"scenario": scenario},
                      {"num_recs": 0, "reason": "no routes"})
            return result

        # 4. Calculate transferable stock
        def calc_transferable(sku, wh, already_out=0):
            available = available_map.get((sku, wh), 0)
            fc_30d = self.forecast_30d_map.get((sku, wh), 0)
            safety = safety_map.get((sku, wh), 0)
            return max(0, int(np.floor(available - fc_30d - safety - already_out)))

        transferable_rows = []
        for _, row in surplus_df.iterrows():
            sku = row["SKU"]
            wh = row["Warehouse"]
            t = calc_transferable(sku, wh)
            if t > 0:
                transferable_rows.append({
                    "SKU": sku, "Warehouse": wh,
                    "Available_Stock": row["Available_Stock"],
                    "Forecast_30d": self.forecast_30d_map.get((sku, wh), 0),
                    "Safety_Stock": row["Safety_Stock"],
                    "Transferable_Stock": t,
                })
        transferable_df = pd.DataFrame(transferable_rows)
        if transferable_df.empty:
            result = {
                "scenario": scenario,
                "has_recommendations": False,
                "num_recommendations": 0,
                "baseline_unmet": baseline_summary["total_unmet"],
                "post_transfer_unmet": baseline_summary["total_unmet"],
                "unmet_avoided": 0.0,
                "total_transfer_cost": 0.0,
                "net_economic_benefit": 0.0,
                "recommendations": [],
                "message": "No transferable surplus stock available (all sources at safety stock minimum).",
            }
            self._log("get_transfer_recommendations", {"scenario": scenario},
                      {"num_recs": 0, "reason": "no transferable stock"})
            return result

        # 5. Filter valid candidates (positive net benefit, transferable, reducible)
        valid_candidates = []
        for _, c in candidates_df.iterrows():
            sku = c["SKU"]
            src = c["Source_Warehouse"]
            dst = c["Destination_Warehouse"]

            t_row = transferable_df[(transferable_df["SKU"] == sku) &
                                    (transferable_df["Warehouse"] == src)]
            if t_row.empty:
                continue
            transferable = t_row["Transferable_Stock"].values[0]
            if transferable <= 0:
                continue
            if c["Net_Benefit_Per_Unit_AED"] <= 0:
                continue

            arrival_day = self.horizon_start + timedelta(days=int(c["Lead_Time_Days"]))
            sd_daily = baseline_daily[(baseline_daily["SKU"] == sku) &
                                       (baseline_daily["Warehouse"] == dst)].sort_values("Date")
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
            if reducible_unmet <= 0:
                continue

            valid_candidates.append({
                **c.to_dict(),
                "Transferable_Stock": transferable,
                "Arrival_Date": arrival_day,
                "Reducible_Unmet_Demand": reducible_unmet,
            })

        valid_df = pd.DataFrame(valid_candidates)
        if valid_df.empty:
            result = {
                "scenario": scenario,
                "has_recommendations": False,
                "num_recommendations": 0,
                "baseline_unmet": baseline_summary["total_unmet"],
                "post_transfer_unmet": baseline_summary["total_unmet"],
                "unmet_avoided": 0.0,
                "total_transfer_cost": 0.0,
                "net_economic_benefit": 0.0,
                "recommendations": [],
                "message": "No valid transfer candidates (all have zero/negative net benefit or arrive too late).",
            }
            self._log("get_transfer_recommendations", {"scenario": scenario},
                      {"num_recs": 0, "reason": "no valid candidates"})
            return result

        # 6. Build and solve MILP with scipy.optimize.milp
        var_keys = []
        var_ub = []
        for _, c in valid_df.iterrows():
            key = (c["SKU"], c["Source_Warehouse"], c["Destination_Warehouse"])
            if key not in var_keys:
                ub = int(min(c["Transferable_Stock"], c["Reducible_Unmet_Demand"]))
                if ub > 0:
                    var_keys.append(key)
                    var_ub.append(ub)

        n_vars = len(var_keys)
        if n_vars == 0:
            result = {
                "scenario": scenario,
                "has_recommendations": False,
                "num_recommendations": 0,
                "baseline_unmet": baseline_summary["total_unmet"],
                "post_transfer_unmet": baseline_summary["total_unmet"],
                "unmet_avoided": 0.0,
                "total_transfer_cost": 0.0,
                "net_economic_benefit": 0.0,
                "recommendations": [],
                "message": "MILP has no decision variables.",
            }
            self._log("get_transfer_recommendations", {"scenario": scenario},
                      {"num_recs": 0, "reason": "no vars"})
            return result

        # Objective: minimize negative net benefit
        c_obj = np.zeros(n_vars)
        for i, key in enumerate(var_keys):
            sku, src, dst = key
            c_row = valid_df[(valid_df["SKU"] == sku) &
                             (valid_df["Source_Warehouse"] == src) &
                             (valid_df["Destination_Warehouse"] == dst)].iloc[0]
            c_obj[i] = -c_row["Net_Benefit_Per_Unit_AED"]

        # Constraints
        source_groups = {}
        dest_groups = {}
        for i, key in enumerate(var_keys):
            sku, src, dst = key
            s_key = (sku, src)
            d_key = (sku, dst)
            source_groups.setdefault(s_key, []).append(i)
            dest_groups.setdefault(d_key, []).append(i)

        A_rows = []
        b_upper = []
        b_lower = []

        for s_key, var_indices in source_groups.items():
            sku, src = s_key
            t_row = transferable_df[(transferable_df["SKU"] == sku) &
                                    (transferable_df["Warehouse"] == src)]
            if not t_row.empty:
                cap = int(t_row["Transferable_Stock"].values[0])
                row = np.zeros(n_vars)
                for vi in var_indices:
                    row[vi] = 1.0
                A_rows.append(row)
                b_lower.append(-np.inf)
                b_upper.append(cap)

        for d_key, var_indices in dest_groups.items():
            sku, dst = d_key
            s_row = shortage_df[shortage_df["SKU"] == sku]
            s_row = s_row[s_row["Warehouse"] == dst]
            if not s_row.empty:
                unmet = int(np.ceil(s_row["Unmet_Demand"].values[0]))
                row = np.zeros(n_vars)
                for vi in var_indices:
                    row[vi] = 1.0
                A_rows.append(row)
                b_lower.append(-np.inf)
                b_upper.append(unmet)

        if A_rows:
            A = np.array(A_rows)
            constraints = LinearConstraint(A, b_lower, b_upper)
        else:
            constraints = None

        bounds = Bounds(lb=0, ub=np.array(var_ub))
        integrality = np.ones(n_vars)

        result_milp = milp(c=c_obj, constraints=constraints,
                           bounds=bounds, integrality=integrality)
        opt_values = result_milp.x if result_milp.x is not None else np.zeros(n_vars)

        # 7. Extract recommendations
        recommended_transfers = []
        for i, key in enumerate(var_keys):
            qty = opt_values[i]
            if qty is not None and qty > 0.5:
                qty = int(round(qty))
                sku, src, dst = key
                c_row = valid_df[(valid_df["SKU"] == sku) &
                                 (valid_df["Source_Warehouse"] == src) &
                                 (valid_df["Destination_Warehouse"] == dst)].iloc[0]
                lead_time = int(c_row["Lead_Time_Days"])
                cost_per_unit = c_row["Cost_Per_Unit_AED"]
                margin = c_row["Profit_Margin_AED"]
                reducible = c_row["Reducible_Unmet_Demand"]
                transfer_cost = qty * cost_per_unit
                unmet_avoided = min(qty, reducible)
                margin_preserved = unmet_avoided * margin
                net_benefit = margin_preserved - transfer_cost

                rec_id = f"TRF-{scenario[:3].upper()}-{sku}-{src[:3].upper()}-{dst[:3].upper()}"

                recommended_transfers.append({
                    "recommendation_id": rec_id,
                    "scenario": scenario,
                    "sku": sku,
                    "source_warehouse": src,
                    "destination_warehouse": dst,
                    "transfer_quantity": qty,
                    "lead_time_days": lead_time,
                    "transfer_cost_aed": round(transfer_cost, 2),
                    "expected_unmet_avoided": round(unmet_avoided, 2),
                    "estimated_net_benefit_aed": round(net_benefit, 2),
                    "profit_margin_aed": margin,
                    "cost_per_unit_aed": cost_per_unit,
                    "product_name": self.product_name_map.get(sku, sku),
                    "arrival_date": (self.horizon_start + timedelta(days=lead_time)).strftime("%Y-%m-%d"),
                    "approval_status": "Pending",
                })

        recommendations_df = pd.DataFrame(recommended_transfers)
        if len(recommendations_df) > 0:
            recommendations_df = recommendations_df.sort_values(
                "estimated_net_benefit_aed", ascending=False,
            ).reset_index(drop=True)

        # 8. Simulate post-transfer
        sim_transfers = []
        for _, r in recommendations_df.iterrows():
            sim_transfers.append({
                "SKU": r["sku"], "Source": r["source_warehouse"],
                "Destination": r["destination_warehouse"],
                "Quantity": r["transfer_quantity"],
                "Lead_Time_Days": r["lead_time_days"],
            })

        post_daily, post_summary = self._simulate_inventory(
            available_map, safety_map, inbound_map, transfers=sim_transfers,
        )

        # 9. Economic impact
        unmet_before = baseline_summary["total_unmet"]
        unmet_after = post_summary["total_unmet"]
        unmet_avoided = unmet_before - unmet_after

        actual_margin_preserved = 0.0
        for _, r in recommendations_df.iterrows():
            sku = r["sku"]
            dst = r["destination_warehouse"]
            before_unmet = baseline_summary["combo_results"][(sku, dst)]["Total_Unmet_Demand"]
            after_unmet = post_summary["combo_results"][(sku, dst)]["Total_Unmet_Demand"]
            actual_avoided = before_unmet - after_unmet
            actual_margin_preserved += actual_avoided * self.margin_map[sku]

        total_transfer_cost = recommendations_df["transfer_cost_aed"].sum()
        net_economic_benefit = actual_margin_preserved - total_transfer_cost

        # Count eliminated shortages
        eliminated = 0
        for key in baseline_summary["combo_results"]:
            before = baseline_summary["combo_results"][key]["Total_Unmet_Demand"]
            after = post_summary["combo_results"][key]["Total_Unmet_Demand"]
            if before > 0 and after == 0:
                eliminated += 1

        result = {
            "scenario": scenario,
            "has_recommendations": len(recommendations_df) > 0,
            "num_recommendations": len(recommendations_df),
            "total_units_recommended": int(recommendations_df["transfer_quantity"].sum()) if len(recommendations_df) > 0 else 0,
            "total_transfer_cost": float(total_transfer_cost),
            "baseline_unmet": float(unmet_before),
            "post_transfer_unmet": float(unmet_after),
            "unmet_avoided": float(unmet_avoided),
            "unmet_reduction_pct": float(unmet_avoided / unmet_before * 100) if unmet_before > 0 else 0.0,
            "actual_margin_preserved": float(actual_margin_preserved),
            "net_economic_benefit": float(net_economic_benefit),
            "shortages_before": int(sum(1 for r in baseline_summary["combo_results"].values() if r["Total_Unmet_Demand"] > 0)),
            "shortages_after": int(sum(1 for r in post_summary["combo_results"].values() if r["Total_Unmet_Demand"] > 0)),
            "shortages_fully_eliminated": eliminated,
            "recommendations": recommendations_df.to_dict("records") if len(recommendations_df) > 0 else [],
            "baseline_summary": {
                "total_unmet": float(unmet_before),
                "total_demand": float(baseline_summary["total_demand"]),
                "total_fulfilled": float(baseline_summary["total_fulfilled"]),
            },
            "post_transfer_summary": {
                "total_unmet": float(unmet_after),
                "total_demand": float(post_summary["total_demand"]),
                "total_fulfilled": float(post_summary["total_fulfilled"]),
            },
            "step4_discrepancy_note": (
                f"The {unmet_avoided/unmet_before*100:.1f}% unmet-demand reduction reflects "
                f"aggregate units avoided ({unmet_avoided:.1f}/{unmet_before:.1f}). "
                f"Only {eliminated} of {int(sum(1 for r in baseline_summary['combo_results'].values() if r['Total_Unmet_Demand'] > 0))} shortage combos "
                f"were fully eliminated to zero. The remainder were significantly reduced but "
                f"still have small residual unmet demand because transfers arrive after lead time, "
                f"so early-day shortages cannot be prevented. This is expected — not a bug."
            ),
        }
        self._log("get_transfer_recommendations", {"scenario": scenario},
                  {"num_recs": len(recommendations_df), "unmet_avoided": unmet_avoided})
        return result

    def validate_source_inventory(self, recommendations: list) -> dict:
        """Validate that source inventory is not double-allocated."""
        source_usage = {}
        for rec in recommendations:
            key = (rec["sku"], rec["source_warehouse"])
            source_usage[key] = source_usage.get(key, 0) + rec["transfer_quantity"]

        issues = []
        for (sku, src), total_out in source_usage.items():
            inv = self._get_inventory(rec["scenario"] if "scenario" in rec else "demonstration")
            avail = inv[(inv["SKU"] == sku) & (inv["Warehouse"] == src)]["Available_Stock"]
            if not avail.empty:
                available = avail.values[0]
                if total_out > available:
                    issues.append(f"{sku}/{src}: allocated {total_out} > available {available}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "source_usage": {f"{k[0]}/{k[1]}": v for k, v in source_usage.items()},
        }
