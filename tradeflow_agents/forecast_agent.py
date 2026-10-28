"""Forecasting Agent — loads and retrieves XGBoost demand forecasts.

Responsibilities:
- Load improved daily and 30-day forecasts
- Retrieve forecasts for specific SKU/warehouse combos
- Summarize predicted demand
- Provide forecast uncertainty (lower/upper bounds)
- Explain model limitations
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
from .database import AgentDatabase


class ForecastingAgent:
    """Agent responsible for demand forecast retrieval and explanation."""

    name = "ForecastingAgent"

    def __init__(self, data_dir: str, db: Optional[AgentDatabase] = None):
        self.data_dir = data_dir
        self.db = db

        self.daily_forecast = pd.read_csv(
            f"{data_dir}/improved_daily_forecasts.csv",
            parse_dates=["Date"],
        )
        self.forecast_30d = pd.read_csv(f"{data_dir}/improved_forecast_30d.csv")
        self.products = pd.read_csv(f"{data_dir}/products.csv")

        self._log("init", {"data_dir": data_dir}, {"status": "initialized"})

    def _log(self, task: str, inputs: dict, outputs: dict,
             status: str = "success", error: str = None):
        if self.db:
            self.db.log_agent_message(self.name, task, inputs, outputs, status, error)

    def get_demand_forecast(self, sku: str, warehouse: str) -> dict:
        """Retrieve forecast data for a specific SKU-warehouse combination.

        Returns daily forecast for 30 days and aggregate 30-day forecast.
        """
        daily = self.daily_forecast[
            (self.daily_forecast["SKU"] == sku)
            & (self.daily_forecast["Warehouse"] == warehouse)
        ].sort_values("Date")

        fc30 = self.forecast_30d[
            (self.forecast_30d["SKU"] == sku)
            & (self.forecast_30d["Warehouse"] == warehouse)
        ]

        if daily.empty or fc30.empty:
            result = {
                "sku": sku,
                "warehouse": warehouse,
                "found": False,
                "error": f"No forecast found for {sku} at {warehouse}",
            }
            self._log("get_demand_forecast",
                      {"sku": sku, "warehouse": warehouse},
                      result, status="error",
                      error=result["error"])
            return result

        fc30_row = fc30.iloc[0]
        daily_list = [
            {"date": str(d["Date"].date()), "predicted_demand": float(d["Predicted_Demand"])}
            for _, d in daily.iterrows()
        ]

        result = {
            "sku": sku,
            "warehouse": warehouse,
            "found": True,
            "forecast_30d": float(fc30_row["Forecast_30d"]),
            "lower_bound": float(fc30_row["Lower_Bound"]),
            "upper_bound": float(fc30_row["Upper_Bound"]),
            "selected_model": str(fc30_row["Selected_Model"]),
            "daily_forecast": daily_list,
            "avg_daily_demand": float(daily["Predicted_Demand"].mean()),
            "max_daily_demand": float(daily["Predicted_Demand"].max()),
            "min_daily_demand": float(daily["Predicted_Demand"].min()),
        }
        self._log("get_demand_forecast",
                  {"sku": sku, "warehouse": warehouse},
                  {"forecast_30d": result["forecast_30d"], "model": result["selected_model"]})
        return result

    def summarize_forecast(self, scenario: str = "all") -> dict:
        """Summarize forecast across all SKU-warehouse combinations."""
        fc = self.forecast_30d.copy()
        total_30d = fc["Forecast_30d"].sum()
        avg_30d = fc["Forecast_30d"].mean()
        max_30d = fc["Forecast_30d"].max()
        min_30d = fc["Forecast_30d"].min()

        # By warehouse
        by_wh = fc.groupby("Warehouse")["Forecast_30d"].agg(["sum", "mean", "count"]).to_dict()

        # By SKU
        by_sku = fc.groupby("SKU")["Forecast_30d"].sum().to_dict()

        # Uncertainty
        fc["uncertainty_range"] = fc["Upper_Bound"] - fc["Lower_Bound"]
        avg_uncertainty = fc["uncertainty_range"].mean()
        avg_uncertainty_pct = (fc["uncertainty_range"] / fc["Forecast_30d"].replace(0, 1)).mean()

        result = {
            "total_30d_demand": float(total_30d),
            "avg_30d_per_combo": float(avg_30d),
            "max_30d": float(max_30d),
            "min_30d": float(min_30d),
            "num_combos": len(fc),
            "by_warehouse": {
                wh: {
                    "total": float(by_wh["sum"][wh]),
                    "avg": float(by_wh["mean"][wh]),
                    "count": int(by_wh["count"][wh]),
                }
                for wh in by_wh["sum"]
            },
            "by_sku": {k: float(v) for k, v in by_sku.items()},
            "avg_uncertainty_range": float(avg_uncertainty),
            "avg_uncertainty_pct": float(avg_uncertainty_pct),
        }
        self._log("summarize_forecast", {"scenario": scenario},
                  {"total_30d": total_30d, "combos": len(fc)})
        return result

    def explain_model_limitations(self) -> dict:
        """Explain the limitations of the forecasting model."""
        limitations = {
            "model_type": "XGBoost (improved with hyperparameter tuning)",
            "key_limitations": [
                "Forecasts are based on historical sales patterns and may not capture sudden market shifts.",
                "Prediction intervals (lower/upper bounds) reflect statistical uncertainty, not operational risk.",
                "Forecast accuracy degrades for SKUs with sparse or highly variable sales history.",
                "The model does not account for promotional events, supply disruptions, or competitor actions.",
                "30-day aggregate forecasts accumulate daily errors — confidence narrows for longer horizons.",
            ],
            "uncertainty_note": (
                "The lower and upper bounds represent prediction intervals. "
                "Actual demand may fall outside this range in rare cases."
            ),
            "recommendation": (
                "Use forecasts as planning guidance, not certainties. "
                "Monitor actual demand vs forecast and retrain periodically."
            ),
        }
        self._log("explain_model_limitations", {}, {"limitations_count": 5})
        return limitations

    def get_all_forecasts(self) -> pd.DataFrame:
        """Return the full 30-day forecast table."""
        return self.forecast_30d.copy()

    def get_daily_forecasts(self) -> pd.DataFrame:
        """Return the full daily forecast table."""
        return self.daily_forecast.copy()
