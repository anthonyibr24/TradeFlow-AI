"""Inventory Risk Agent — analyzes inventory against forecast demand.

Responsibilities:
- Analyze inventory levels against forecast demand
- Identify critical shortages, excess stock, ageing risks
- Compare original and demonstration scenarios
- Return structured inventory risk reports
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from .database import AgentDatabase


class InventoryRiskAgent:
    """Agent responsible for inventory risk analysis."""

    name = "InventoryRiskAgent"

    def __init__(self, data_dir: str, db: Optional[AgentDatabase] = None):
        self.data_dir = data_dir
        self.db = db

        # Load both scenarios
        self.scenario_inventory = pd.read_csv(f"{data_dir}/scenario_inventory.csv")
        self.original_inventory = pd.read_csv(f"{data_dir}/inventory.csv")
        self.forecast_30d = pd.read_csv(f"{data_dir}/improved_forecast_30d.csv")
        self.daily_forecast = pd.read_csv(
            f"{data_dir}/improved_daily_forecasts.csv", parse_dates=["Date"],
        )
        self.products = pd.read_csv(f"{data_dir}/products.csv")
        self.warehouses = pd.read_csv(f"{data_dir}/warehouses.csv")

        # Scenario-specific files
        self.scenario_inbound = pd.read_csv(
            f"{data_dir}/scenario_inbound_orders.csv",
            parse_dates=["Expected_Arrival"],
        )
        self.scenario_stock_ageing = pd.read_csv(f"{data_dir}/scenario_stock_ageing.csv")

        # Original files
        self.original_inbound = pd.read_csv(
            f"{data_dir}/inbound_orders.csv",
            parse_dates=["Expected_Arrival"],
        )
        self.original_stock_ageing = pd.read_csv(f"{data_dir}/stock_ageing.csv")

        # Risk files if they exist
        import os
        sr_path = f"{data_dir}/scenario_inventory_risks.csv"
        self.scenario_risks = pd.read_csv(sr_path) if os.path.exists(sr_path) else None
        or_path = f"{data_dir}/inventory_risks.csv"
        self.original_risks = pd.read_csv(or_path) if os.path.exists(or_path) else None

        self._log("init", {"data_dir": data_dir}, {"status": "initialized"})

    def _log(self, task: str, inputs: dict, outputs: dict,
             status: str = "success", error: str = None):
        if self.db:
            self.db.log_agent_message(self.name, task, inputs, outputs, status, error)

    def analyze_inventory(self, scenario: str = "demonstration") -> dict:
        """Analyze inventory risks for the specified scenario.

        Parameters
        ----------
        scenario : str
            "demonstration" or "original"

        Returns
        -------
        dict with risk analysis results
        """
        if scenario == "demonstration":
            inv = self.scenario_inventory.copy()
            inbound = self.scenario_inbound.copy()
            ageing = self.scenario_stock_ageing.copy()
            risks = self.scenario_risks
            risk_file = "scenario_inventory_risks.csv"
        elif scenario == "original":
            inv = self.original_inventory.copy()
            inbound = self.original_inbound.copy()
            ageing = self.original_stock_ageing.copy()
            risks = self.original_risks
            risk_file = "inventory_risks.csv"
        else:
            result = {"error": f"Unknown scenario: {scenario}", "valid": ["demonstration", "original"]}
            self._log("analyze_inventory", {"scenario": scenario}, result,
                      status="error", error=result["error"])
            return result

        # Merge forecast
        inv = inv.merge(
            self.forecast_30d[["SKU", "Warehouse", "Forecast_30d"]],
            on=["SKU", "Warehouse"],
            how="left",
        )

        # Calculate coverage
        inv["Coverage_Ratio"] = inv["Available_Stock"] / inv["Forecast_30d"].replace(0, np.nan)
        inv["Unmet_Demand"] = (inv["Forecast_30d"] - inv["Available_Stock"]).clip(lower=0)
        inv["Excess_Stock"] = (inv["Available_Stock"] - inv["Forecast_30d"] - inv["Safety_Stock"]).clip(lower=0)

        # Risk classification
        def classify(row):
            if row["Unmet_Demand"] > 0:
                return "Critical"
            elif row["Available_Stock"] < row["Safety_Stock"]:
                return "Warning"
            elif row["Excess_Stock"] > 100:
                return "Excess"
            else:
                return "Healthy"

        inv["Risk_Class"] = inv.apply(classify, axis=1)

        # Aggregate inbound per combo
        inbound_agg = inbound.groupby(["SKU", "Warehouse"])["Quantity"].sum().reset_index()
        inbound_agg.rename(columns={"Quantity": "Total_Incoming"}, inplace=True)
        inv = inv.merge(inbound_agg, on=["SKU", "Warehouse"], how="left")
        inv["Total_Incoming"] = inv["Total_Incoming"].fillna(0)

        # Ageing summary
        ageing_summary = ageing.groupby(["SKU", "Warehouse"]).agg(
            Age_0_30=("Quantity", lambda x: x[ageing.loc[x.index, "Age_Bucket"] == "0-30"].sum()),
            Age_31_60=("Quantity", lambda x: x[ageing.loc[x.index, "Age_Bucket"] == "31-60"].sum()),
            Age_61_90=("Quantity", lambda x: x[ageing.loc[x.index, "Age_Bucket"] == "61-90"].sum()),
            Age_90_Plus=("Quantity", lambda x: x[ageing.loc[x.index, "Age_Bucket"] == "90+"].sum()),
        ).reset_index()
        ageing_summary["Total_Aged_60_Plus"] = ageing_summary["Age_61_90"] + ageing_summary["Age_90_Plus"]
        ageing_summary["Aged_Pct"] = (
            ageing_summary["Total_Aged_60_Plus"] /
            ageing_summary[["Age_0_30", "Age_31_60", "Age_61_90", "Age_90_Plus"]].sum(axis=1).replace(0, 1)
        )
        inv = inv.merge(ageing_summary, on=["SKU", "Warehouse"], how="left")

        # Summary stats
        risk_counts = inv["Risk_Class"].value_counts().to_dict()
        total_unmet = float(inv["Unmet_Demand"].sum())
        total_excess = float(inv["Excess_Stock"].sum())
        total_available = int(inv["Available_Stock"].sum())
        total_forecast = float(inv["Forecast_30d"].sum())

        # By warehouse
        by_wh = {}
        for wh in inv["Warehouse"].unique():
            wh_data = inv[inv["Warehouse"] == wh]
            by_wh[wh] = {
                "combos": len(wh_data),
                "critical": int((wh_data["Risk_Class"] == "Critical").sum()),
                "warning": int((wh_data["Risk_Class"] == "Warning").sum()),
                "excess": int((wh_data["Risk_Class"] == "Excess").sum()),
                "healthy": int((wh_data["Risk_Class"] == "Healthy").sum()),
                "total_unmet": float(wh_data["Unmet_Demand"].sum()),
                "total_excess": float(wh_data["Excess_Stock"].sum()),
            }

        # Critical combos detail
        critical_combos = inv[inv["Risk_Class"] == "Critical"][
            ["SKU", "Warehouse", "Available_Stock", "Forecast_30d", "Safety_Stock",
             "Unmet_Demand", "Coverage_Ratio"]
        ].to_dict("records")

        # Ageing risks
        high_ageing = inv[inv["Aged_Pct"] > 0.3][
            ["SKU", "Warehouse", "Aged_Pct", "Total_Aged_60_Plus"]
        ].to_dict("records")

        result = {
            "scenario": scenario,
            "total_combos": len(inv),
            "risk_counts": risk_counts,
            "total_available_stock": total_available,
            "total_forecast_30d": total_forecast,
            "total_unmet_demand": total_unmet,
            "total_excess_stock": total_excess,
            "coverage_ratio": total_available / total_forecast if total_forecast > 0 else 0,
            "by_warehouse": by_wh,
            "critical_combos": critical_combos,
            "high_ageing_combos": high_ageing,
            "has_shortages": total_unmet > 0,
            "has_excess": total_excess > 0,
        }
        self._log("analyze_inventory", {"scenario": scenario},
                  {"risk_counts": risk_counts, "unmet": total_unmet})
        return result

    def compare_scenarios(self) -> dict:
        """Compare original and demonstration scenarios."""
        demo = self.analyze_inventory("demonstration")
        orig = self.analyze_inventory("original")

        result = {
            "original": {
                "risk_counts": orig["risk_counts"],
                "total_unmet": orig["total_unmet_demand"],
                "total_excess": orig["total_excess_stock"],
                "coverage_ratio": orig["coverage_ratio"],
            },
            "demonstration": {
                "risk_counts": demo["risk_counts"],
                "total_unmet": demo["total_unmet_demand"],
                "total_excess": demo["total_excess_stock"],
                "coverage_ratio": demo["coverage_ratio"],
            },
            "comparison": {
                "unmet_demand_change": demo["total_unmet_demand"] - orig["total_unmet_demand"],
                "excess_stock_change": demo["total_excess_stock"] - orig["total_excess_stock"],
                "coverage_ratio_change": demo["coverage_ratio"] - orig["coverage_ratio"],
                "note": (
                    "The demonstration scenario was designed to show shortages and transfer "
                    "opportunities. The original scenario has heavy overstocking and ageing."
                ),
            },
        }
        self._log("compare_scenarios", {},
                  {"demo_unmet": demo["total_unmet_demand"], "orig_unmet": orig["total_unmet_demand"]})
        return result

    def get_risk_report(self, scenario: str = "demonstration") -> dict:
        """Return a structured risk report combining analysis and recommendations."""
        analysis = self.analyze_inventory(scenario)

        recommendations = []
        if analysis.get("has_shortages"):
            recommendations.append({
                "type": "shortage",
                "priority": "high",
                "message": f"{len(analysis['critical_combos'])} SKU-warehouse combinations "
                           f"face critical shortages totaling {analysis['total_unmet_demand']:.0f} units.",
                "action": "Evaluate inter-warehouse transfers to reduce unmet demand.",
            })
        if analysis.get("has_excess"):
            recommendations.append({
                "type": "excess",
                "priority": "medium",
                "message": f"Excess inventory of {analysis['total_excess_stock']:.0f} units detected. "
                           f"Consider redistributing or liquidating aged stock.",
                "action": "Review excess stock for transfer or clearance.",
            })
        if analysis.get("high_ageing_combos"):
            recommendations.append({
                "type": "ageing",
                "priority": "medium",
                "message": f"{len(analysis['high_ageing_combos'])} combinations have >30% stock aged 60+ days.",
                "action": "Prioritize dispatching aged stock to reduce holding costs.",
            })

        report = {
            "scenario": scenario,
            "analysis": analysis,
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat(),
        }
        self._log("get_risk_report", {"scenario": scenario},
                  {"recommendations_count": len(recommendations)})
        return report
