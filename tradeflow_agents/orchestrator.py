"""Orchestrator Agent — coordinates all agents in the workflow.

Coordinates the Forecasting, Inventory Risk, Optimization, Explanation,
and Approval agents. Supports calling individual agents as needed
rather than always executing every step.

Workflow:
1. User selects an inventory scenario
2. Forecasting Agent retrieves demand predictions
3. Inventory Agent identifies risks
4. Optimization Agent evaluates transfer opportunities
5. Explanation Agent explains recommendations
6. Approval Agent presents recommendations for review
7. User approves or rejects recommendations
8. System updates and reports impact
"""

import pandas as pd
from datetime import datetime
from typing import Optional
from .database import AgentDatabase
from .forecast_agent import ForecastingAgent
from .inventory_agent import InventoryRiskAgent
from .optimization_agent import OptimizationAgent
from .explanation_agent import ExplanationAgent
from .approval_agent import ApprovalAgent


VALID_SCENARIOS = ["demonstration", "original"]


class OrchestratorAgent:
    """Coordinates all agents in the TradeFlow AI workflow."""

    name = "OrchestratorAgent"

    def __init__(self, data_dir: str, db_path: Optional[str] = None):
        self.data_dir = data_dir
        self.db = AgentDatabase(db_path)

        # Initialize all agents
        self.forecast_agent = ForecastingAgent(data_dir, db=self.db)
        self.inventory_agent = InventoryRiskAgent(data_dir, db=self.db)
        self.optimization_agent = OptimizationAgent(data_dir, db=self.db)
        self.explanation_agent = ExplanationAgent(
            data_dir, db=self.db, optimization_agent=self.optimization_agent,
        )
        self.approval_agent = ApprovalAgent(db=self.db)

        self.current_scenario = None
        self.last_optimization_result = None

        self._log("init", {"data_dir": data_dir}, {
            "agents": [
                self.forecast_agent.name,
                self.inventory_agent.name,
                self.optimization_agent.name,
                self.explanation_agent.name,
                self.approval_agent.name,
            ],
        })

    def _log(self, task: str, inputs: dict, outputs: dict,
             status: str = "success", error: str = None):
        self.db.log_agent_message(self.name, task, inputs, outputs, status, error)

    def get_demand_forecast(self, sku: str, warehouse: str) -> dict:
        """Retrieve demand forecast for a specific SKU-warehouse combo."""
        return self.forecast_agent.get_demand_forecast(sku, warehouse)

    def analyze_inventory(self, scenario: str = "demonstration") -> dict:
        """Analyze inventory risks for a scenario."""
        if scenario not in VALID_SCENARIOS:
            return {"error": f"Invalid scenario: {scenario}", "valid": VALID_SCENARIOS}
        self.current_scenario = scenario
        return self.inventory_agent.analyze_inventory(scenario)

    def get_transfer_recommendations(self, scenario: str = "demonstration",
                                     force_reload: bool = False) -> dict:
        """Run optimization and get transfer recommendations for a scenario.

        Parameters
        ----------
        scenario : str — "demonstration" or "original"
        force_reload : bool — if True, reload recommendations into the approval
            system (clearing existing decisions). If False (default), only load
            when no recommendations exist yet, preserving existing approval decisions.
        """
        if scenario not in VALID_SCENARIOS:
            return {"error": f"Invalid scenario: {scenario}", "valid": VALID_SCENARIOS}

        self.current_scenario = scenario
        result = self.optimization_agent.get_transfer_recommendations(scenario)
        self.last_optimization_result = result

        # Load into approval system only if:
        # 1. force_reload=True (explicit regeneration), OR
        # 2. No recommendations exist yet for this scenario
        if result.get("has_recommendations"):
            existing_recs = self.approval_agent.get_all_approvals(scenario=scenario)
            if force_reload or not existing_recs:
                self.approval_agent.load_recommendations(
                    result["recommendations"], scenario,
                    clear_existing=force_reload,
                )

        self._log("get_transfer_recommendations", {"scenario": scenario},
                  {"num_recs": result.get("num_recommendations", 0),
                   "unmet_avoided": result.get("unmet_avoided", 0)})
        return result

    def explain_transfer(self, transfer_id: str) -> dict:
        """Explain a specific transfer recommendation."""
        # Get the recommendation from the approval agent
        rec = self.approval_agent.get_approval_status(transfer_id)
        if not rec.get("found"):
            return rec

        # Get full recommendation data
        full_rec = self.db.get_recommendation(transfer_id)
        if full_rec is None:
            return {"error": f"Recommendation not found: {transfer_id}"}

        # Transform to the format expected by explanation agent
        rec_for_explanation = {
            "sku": full_rec["sku"],
            "source_warehouse": full_rec["source_warehouse"],
            "destination_warehouse": full_rec["destination_warehouse"],
            "transfer_quantity": full_rec["transfer_quantity"],
            "lead_time_days": full_rec["lead_time_days"],
            "transfer_cost_aed": full_rec["transfer_cost_aed"],
            "expected_unmet_avoided": full_rec["expected_unmet_avoided"],
            "estimated_net_benefit_aed": full_rec["estimated_net_benefit_aed"],
        }

        return self.explanation_agent.explain_transfer(
            transfer_id, rec_for_explanation, self.last_optimization_result,
        )

    def approve_transfer(self, transfer_id: str, decided_by: str = "user",
                         note: str = "") -> dict:
        """Approve a transfer recommendation."""
        return self.approval_agent.approve_transfer(transfer_id, decided_by, note)

    def reject_transfer(self, transfer_id: str, decided_by: str = "user",
                        note: str = "") -> dict:
        """Reject a transfer recommendation."""
        return self.approval_agent.reject_transfer(transfer_id, decided_by, note)

    def get_system_summary(self, scenario: str = "demonstration") -> dict:
        """Get a comprehensive system summary for a scenario."""
        if scenario not in VALID_SCENARIOS:
            return {"error": f"Invalid scenario: {scenario}", "valid": VALID_SCENARIOS}

        # Gather info from each agent
        forecast_summary = self.forecast_agent.summarize_forecast(scenario)
        inventory_analysis = self.inventory_agent.analyze_inventory(scenario)
        approval_summary = self.approval_agent.get_approval_summary(scenario)

        # Use cached optimization result if available, otherwise run optimization
        if (self.last_optimization_result and
            self.last_optimization_result.get("scenario") == scenario):
            opt_result = self.last_optimization_result
        else:
            opt_result = self.optimization_agent.get_transfer_recommendations(scenario)
            self.last_optimization_result = opt_result

        # Generate explanation summary
        explanation_summary = self.explanation_agent.explain_system_summary(opt_result)

        result = {
            "scenario": scenario,
            "generated_at": datetime.now().isoformat(),
            "forecast": {
                "total_30d_demand": forecast_summary["total_30d_demand"],
                "num_combos": forecast_summary["num_combos"],
                "avg_uncertainty_pct": forecast_summary["avg_uncertainty_pct"],
            },
            "inventory": {
                "risk_counts": inventory_analysis["risk_counts"],
                "total_unmet_demand": inventory_analysis["total_unmet_demand"],
                "total_excess_stock": inventory_analysis["total_excess_stock"],
                "coverage_ratio": inventory_analysis["coverage_ratio"],
                "by_warehouse": inventory_analysis["by_warehouse"],
            },
            "optimization": {
                "has_recommendations": opt_result.get("has_recommendations", False),
                "num_recommendations": opt_result.get("num_recommendations", 0),
                "total_units_recommended": opt_result.get("total_units_recommended", 0),
                "total_transfer_cost": opt_result.get("total_transfer_cost", 0),
                "baseline_unmet": opt_result.get("baseline_unmet", 0),
                "post_transfer_unmet": opt_result.get("post_transfer_unmet", 0),
                "unmet_avoided": opt_result.get("unmet_avoided", 0),
                "unmet_reduction_pct": opt_result.get("unmet_reduction_pct", 0),
                "net_economic_benefit": opt_result.get("net_economic_benefit", 0),
                "shortages_fully_eliminated": opt_result.get("shortages_fully_eliminated", 0),
            },
            "approval": approval_summary,
            "explanation": explanation_summary["summary"],
            "step4_discrepancy_note": opt_result.get("step4_discrepancy_note"),
        }
        self._log("get_system_summary", {"scenario": scenario},
                  {"num_recs": opt_result.get("num_recommendations", 0),
                   "unmet_avoided": opt_result.get("unmet_avoided", 0)})
        return result

    def run_full_workflow(self, scenario: str = "demonstration") -> dict:
        """Execute the complete workflow for a scenario.

        Steps:
        1. Retrieve forecasts
        2. Analyze inventory risks
        3. Run optimization
        4. Generate explanations
        5. Load into approval system
        """
        if scenario not in VALID_SCENARIOS:
            return {"error": f"Invalid scenario: {scenario}", "valid": VALID_SCENARIOS}

        self.current_scenario = scenario
        results = {"scenario": scenario, "started_at": datetime.now().isoformat()}

        # Step 1: Forecast
        results["forecast"] = self.forecast_agent.summarize_forecast(scenario)

        # Step 2: Inventory risk
        results["inventory"] = self.inventory_agent.analyze_inventory(scenario)

        # Step 3: Optimization
        opt_result = self.optimization_agent.get_transfer_recommendations(scenario)
        self.last_optimization_result = opt_result
        results["optimization"] = opt_result

        # Step 4: Explanations
        if opt_result.get("has_recommendations"):
            explanations = self.explanation_agent.explain_all_transfers(
                opt_result["recommendations"], opt_result,
            )
            results["explanations"] = explanations

            # Step 5: Load into approval system (preserve existing decisions)
            approval_result = self.approval_agent.load_recommendations(
                opt_result["recommendations"], scenario,
                clear_existing=False,
            )
            results["approval_loaded"] = approval_result
        else:
            results["explanations"] = []
            results["approval_loaded"] = {"loaded": 0, "scenario": scenario}

        results["completed_at"] = datetime.now().isoformat()
        results["summary"] = self.get_system_summary(scenario)

        self._log("run_full_workflow", {"scenario": scenario},
                  {"num_recs": opt_result.get("num_recommendations", 0),
                   "unmet_avoided": opt_result.get("unmet_avoided", 0)})
        return results

    def compare_scenarios(self) -> dict:
        """Compare the original and demonstration scenarios."""
        return self.inventory_agent.compare_scenarios()

    def get_agent_log(self, limit: int = 100) -> list:
        """Get the agent communication log."""
        return self.db.get_agent_messages(limit=limit)

    def export_agent_log(self, csv_path: str):
        """Export the agent communication log to CSV."""
        self.db.export_agent_log(csv_path)

    def get_audit_trail(self, limit: int = 100) -> list:
        """Get the audit trail."""
        return self.approval_agent.get_audit_trail(limit=limit)

    def close(self):
        """Clean up resources."""
        pass
