"""Explanation Agent — generates clear explanations for transfer recommendations.

Responsibilities:
- Generate clear explanations for each transfer recommendation
- Explain why a source warehouse was selected
- Explain expected shortage reduction
- Explain transfer costs and projected benefits
- Explain assumptions and uncertainty

Uses deterministic calculations from optimization results.
Does NOT invent financial figures. All numbers come from actual optimization output.
"""

import pandas as pd
from typing import Optional
from .database import AgentDatabase


class ExplanationAgent:
    """Agent responsible for generating human-readable explanations."""

    name = "ExplanationAgent"

    def __init__(self, data_dir: str, db: Optional[AgentDatabase] = None,
                 optimization_agent=None):
        self.data_dir = data_dir
        self.db = db
        self.opt_agent = optimization_agent

        self.products = pd.read_csv(f"{data_dir}/products.csv")
        self.transfer_routes = pd.read_csv(f"{data_dir}/transfer_routes.csv")
        self.forecast_30d = pd.read_csv(f"{data_dir}/improved_forecast_30d.csv")

        self.product_name_map = self.products.set_index("SKU")["Product"].to_dict()
        self.margin_map = self.products.set_index("SKU")["Profit_Margin_AED"].to_dict()
        self.holding_cost_map = self.products.set_index("SKU")["Holding_Cost_Per_Unit_Day_AED"].to_dict()

        self._log("init", {"data_dir": data_dir}, {"status": "initialized"})

    def _log(self, task: str, inputs: dict, outputs: dict,
             status: str = "success", error: str = None):
        if self.db:
            self.db.log_agent_message(self.name, task, inputs, outputs, status, error)

    def explain_transfer(self, transfer_id: str, recommendation: dict = None,
                          optimization_result: dict = None) -> dict:
        """Generate a detailed explanation for a single transfer recommendation.

        Parameters
        ----------
        transfer_id : str
            The recommendation ID.
        recommendation : dict, optional
            The recommendation data (if already available).
        optimization_result : dict, optional
            Full optimization result for context (baseline, post-transfer).

        Returns
        -------
        dict with structured explanation
        """
        if recommendation is None:
            return {
                "transfer_id": transfer_id,
                "found": False,
                "error": "Recommendation not provided. Pass recommendation data to explain_transfer().",
            }

        sku = recommendation.get("sku", recommendation.get("SKU", ""))
        src = recommendation.get("source_warehouse", recommendation.get("Source_Warehouse", ""))
        dst = recommendation.get("destination_warehouse", recommendation.get("Destination_Warehouse", ""))
        qty = recommendation.get("transfer_quantity", recommendation.get("Transfer_Quantity", 0))
        lead_time = recommendation.get("lead_time_days", recommendation.get("Lead_Time_Days", 0))
        cost = recommendation.get("transfer_cost_aed", recommendation.get("Transfer_Cost_AED", 0))
        unmet_avoided = recommendation.get("expected_unmet_avoided",
                                          recommendation.get("Expected_Unmet_Demand_Avoided", 0))
        net_benefit = recommendation.get("estimated_net_benefit_aed",
                                        recommendation.get("Estimated_Net_Benefit_AED", 0))
        margin = recommendation.get("profit_margin_aed",
                                   self.margin_map.get(sku, 0))

        product_name = self.product_name_map.get(sku, sku)
        cost_per_unit = cost / qty if qty > 0 else 0

        # Build explanation components
        source_selection = (
            f"{src} was selected as the source because it holds transferable surplus stock "
            f"of {product_name} ({sku}) — inventory above its own forecast demand and safety "
            f"stock requirements. Transferring from {src} does not create new shortages there."
        )

        shortage_reduction = (
            f"{dst} faces a projected shortage of {unmet_avoided:.0f} units over the 30-day "
            f"planning horizon. Transferring {qty} units from {src} is expected to reduce "
            f"this unmet demand by approximately {unmet_avoided:.0f} units (capped at the "
            f"reducible portion after lead time). The transfer arrives in {lead_time} day(s), "
            f"so shortages occurring before arrival cannot be prevented."
        )

        cost_benefit = (
            f"Transfer cost: {cost:.2f} AED ({cost_per_unit:.2f} AED/unit x {qty} units). "
            f"Profit margin per unit: {margin:.2f} AED. "
            f"Projected margin preserved: {unmet_avoided * margin:.2f} AED. "
            f"Projected net economic benefit: {net_benefit:.2f} AED "
            f"(margin preserved minus transfer cost). "
            f"All figures are projected estimates from simulation, not realized savings."
        )

        assumptions = (
            "Assumptions: (1) Transfers are dispatched at the start of the planning horizon. "
            "(2) Source safety stock is preserved — only excess stock is transferred. "
            "(3) Daily demand follows the XGBoost forecast, which carries statistical uncertainty. "
            "(4) Transfer lead time is fixed per route. "
            "(5) No simultaneous demand surges or supply disruptions are modeled. "
            "(6) Economic benefits are projected estimates and require human approval before execution."
        )

        uncertainty = (
            "Uncertainty: Forecast demand has prediction intervals (lower/upper bounds). "
            "Actual demand may deviate from the point forecast, which would affect the actual "
            "unmet demand avoided and the realized economic benefit. The transfer cost is fixed "
            "and known; the benefit is a projected estimate."
        )

        reason = (
            f"Recommendation: Transfer {qty} units of {product_name} ({sku}) from {src} to {dst}. "
            f"This transfer is projected to avoid {unmet_avoided:.0f} units of unmet demand, "
            f"preserving approximately {unmet_avoided * margin:.2f} AED in contribution margin "
            f"at a transfer cost of {cost:.2f} AED, yielding a projected net benefit of "
            f"{net_benefit:.2f} AED. The transfer arrives in {lead_time} day(s). "
            f"Approval status: Pending. No transfer will be executed without human approval."
        )

        explanation = {
            "transfer_id": transfer_id,
            "found": True,
            "explanation_type": "deterministic",
            "sku": sku,
            "product_name": product_name,
            "source_warehouse": src,
            "destination_warehouse": dst,
            "transfer_quantity": qty,
            "lead_time_days": lead_time,
            "transfer_cost_aed": cost,
            "cost_per_unit_aed": cost_per_unit,
            "expected_unmet_avoided": unmet_avoided,
            "profit_margin_aed": margin,
            "projected_margin_preserved": unmet_avoided * margin,
            "estimated_net_benefit_aed": net_benefit,
            "source_selection_reason": source_selection,
            "shortage_reduction_reason": shortage_reduction,
            "cost_benefit_reason": cost_benefit,
            "assumptions": assumptions,
            "uncertainty": uncertainty,
            "reason_for_recommendation": reason,
        }

        self._log("explain_transfer", {"transfer_id": transfer_id},
                  {"explanation_type": "deterministic", "net_benefit": net_benefit})
        return explanation

    def explain_all_transfers(self, recommendations: list,
                               optimization_result: dict = None) -> list:
        """Generate explanations for all recommendations."""
        explanations = []
        for rec in recommendations:
            tid = rec.get("recommendation_id",
                          f"TRF-{rec.get('sku','')}-{rec.get('source_warehouse','')}-{rec.get('destination_warehouse','')}")
            exp = self.explain_transfer(tid, rec, optimization_result)
            explanations.append(exp)
        self._log("explain_all_transfers", {"count": len(recommendations)},
                  {"explanations_count": len(explanations)})
        return explanations

    def explain_system_summary(self, optimization_result: dict) -> dict:
        """Generate a high-level summary explanation of the optimization results."""
        scenario = optimization_result.get("scenario", "unknown")
        num_recs = optimization_result.get("num_recommendations", 0)
        baseline_unmet = optimization_result.get("baseline_unmet", 0)
        post_unmet = optimization_result.get("post_transfer_unmet", 0)
        unmet_avoided = optimization_result.get("unmet_avoided", 0)
        reduction_pct = optimization_result.get("unmet_reduction_pct", 0)
        net_benefit = optimization_result.get("net_economic_benefit", 0)
        total_cost = optimization_result.get("total_transfer_cost", 0)
        eliminated = optimization_result.get("shortages_fully_eliminated", 0)
        shortages_before = optimization_result.get("shortages_before", 0)

        if num_recs == 0:
            summary = (
                f"No transfer recommendations were generated for the {scenario} scenario. "
                f"This may be because there are no projected shortages, no transferable surplus, "
                f"or no economically beneficial transfer routes."
            )
        else:
            summary = (
                f"The optimization agent identified {num_recs} transfer recommendations for the "
                f"{scenario} scenario. These transfers are projected to reduce unmet demand from "
                f"{baseline_unmet:.0f} to {post_unmet:.0f} units ({reduction_pct:.1f}% reduction). "
                f"{eliminated} of {shortages_before} shortage combos are projected to be fully "
                f"eliminated; the remainder are significantly reduced but still have small residual "
                f"unmet demand due to transfer lead times. "
                f"Total transfer cost: {total_cost:.2f} AED. "
                f"Projected net economic benefit: {net_benefit:.2f} AED. "
                f"All benefits are projected estimates and require human approval."
            )

        result = {
            "scenario": scenario,
            "summary_type": "deterministic",
            "summary": summary,
            "key_metrics": {
                "num_recommendations": num_recs,
                "baseline_unmet": baseline_unmet,
                "post_transfer_unmet": post_unmet,
                "unmet_avoided": unmet_avoided,
                "reduction_pct": reduction_pct,
                "total_transfer_cost": total_cost,
                "net_economic_benefit": net_benefit,
                "shortages_fully_eliminated": eliminated,
            },
            "note": "This is a deterministic summary generated from actual optimization results.",
        }
        self._log("explain_system_summary", {"scenario": scenario},
                  {"num_recs": num_recs, "net_benefit": net_benefit})
        return result
