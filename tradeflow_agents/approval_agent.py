"""Approval Agent — manages human approval workflow for transfers.

Responsibilities:
- Present proposed transfers for human approval
- Allow approval and rejection
- Track approval status
- Prevent duplicate approval actions
- Record decisions with timestamps
- Maintain an audit log

Does NOT execute physical warehouse transfers.
Approval only updates the simulated workflow state.
"""

import pandas as pd
from datetime import datetime
from typing import Optional
from .database import AgentDatabase


class ApprovalAgent:
    """Agent responsible for managing transfer approval workflow."""

    name = "ApprovalAgent"

    def __init__(self, db: AgentDatabase):
        self.db = db
        self._log("init", {}, {"status": "initialized"})

    def _log(self, task: str, inputs: dict, outputs: dict,
             status: str = "success", error: str = None):
        self.db.log_agent_message(self.name, task, inputs, outputs, status, error)

    def load_recommendations(self, recommendations: list, scenario: str,
                             clear_existing: bool = False):
        """Load transfer recommendations into the approval system.

        Parameters
        ----------
        recommendations : list — recommendation dicts from the optimizer
        scenario : str — scenario name
        clear_existing : bool — if True, clears all existing recommendations first
            (use only for explicit regeneration). If False (default), preserves
            existing approval decisions for unchanged recommendations.
        """
        if clear_existing:
            self.db.clear_recommendations(scenario)

        # Track which rec IDs are in the new set
        new_ids = {rec["recommendation_id"] for rec in recommendations}

        # If not clearing, flag any existing recs that are no longer in the new set
        if not clear_existing:
            existing_recs = self.db.get_all_recommendations(scenario=scenario)
            stale = [r for r in existing_recs
                     if r["recommendation_id"] not in new_ids]
            for r in stale:
                self._log("load_recommendations", {"scenario": scenario},
                          {"stale_rec": r["recommendation_id"],
                           "note": "Recommendation no longer in optimizer output — "
                                   "existing decision preserved but may need review"},
                          status="warning")

        loaded = 0
        for rec in recommendations:
            rec_data = {
                "recommendation_id": rec["recommendation_id"],
                "scenario": scenario,
                "sku": rec["sku"],
                "source_warehouse": rec["source_warehouse"],
                "destination_warehouse": rec["destination_warehouse"],
                "transfer_quantity": rec["transfer_quantity"],
                "lead_time_days": rec["lead_time_days"],
                "transfer_cost_aed": rec["transfer_cost_aed"],
                "expected_unmet_avoided": rec["expected_unmet_avoided"],
                "estimated_net_benefit_aed": rec["estimated_net_benefit_aed"],
                "explanation": rec.get("explanation", ""),
                "approval_status": "Pending",
            }
            self.db.save_recommendation(rec_data)
            loaded += 1

        self._log("load_recommendations", {"scenario": scenario, "count": len(recommendations),
                                           "clear_existing": clear_existing},
                  {"loaded": loaded})
        return {"loaded": loaded, "scenario": scenario,
                "cleared": clear_existing}

    def get_pending_approvals(self, scenario: str = None) -> list:
        """Get all pending transfer recommendations."""
        recs = self.db.get_all_recommendations(scenario=scenario, status="Pending")
        self._log("get_pending_approvals", {"scenario": scenario},
                  {"count": len(recs)})
        return recs

    def get_all_approvals(self, scenario: str = None) -> list:
        """Get all transfer recommendations regardless of status."""
        recs = self.db.get_all_recommendations(scenario=scenario)
        self._log("get_all_approvals", {"scenario": scenario},
                  {"count": len(recs)})
        return recs

    def approve_transfer(self, transfer_id: str, decided_by: str = "user",
                         note: str = "") -> dict:
        """Approve a transfer recommendation.

        Returns dict with success status and message.
        Prevents duplicate approvals and rejection overrides.
        """
        rec = self.db.get_recommendation(transfer_id)
        if rec is None:
            result = {"success": False, "error": f"Invalid transfer ID: {transfer_id}"}
            self._log("approve_transfer", {"transfer_id": transfer_id},
                      result, status="error", error=result["error"])
            return result

        old_status = rec["approval_status"]

        if old_status == "Approved":
            result = {
                "success": False,
                "error": "Duplicate approval prevented",
                "message": f"Transfer {transfer_id} is already approved.",
                "current_status": "Approved",
            }
            self._log("approve_transfer", {"transfer_id": transfer_id},
                      result, status="warning", error="duplicate approval")
            return result

        if old_status == "Rejected":
            result = {
                "success": False,
                "error": "Cannot approve a rejected transfer",
                "message": f"Transfer {transfer_id} was already rejected. "
                           f"Rejection decisions are final.",
                "current_status": "Rejected",
            }
            self._log("approve_transfer", {"transfer_id": transfer_id},
                      result, status="warning", error="cannot override rejection")
            return result

        updated = self.db.update_approval_status(transfer_id, "Approved",
                                                 decided_by=decided_by, note=note)
        if updated:
            result = {
                "success": True,
                "transfer_id": transfer_id,
                "previous_status": old_status,
                "new_status": "Approved",
                "decided_by": decided_by,
                "timestamp": datetime.now().isoformat(),
                "message": f"Transfer {transfer_id} approved successfully.",
            }
        else:
            result = {
                "success": False,
                "error": "Failed to update approval status",
                "transfer_id": transfer_id,
            }
        self._log("approve_transfer", {"transfer_id": transfer_id},
                  {"success": result["success"], "new_status": result.get("new_status")})
        return result

    def reject_transfer(self, transfer_id: str, decided_by: str = "user",
                        note: str = "") -> dict:
        """Reject a transfer recommendation.

        Returns dict with success status and message.
        Prevents duplicate rejections and approval overrides.
        """
        rec = self.db.get_recommendation(transfer_id)
        if rec is None:
            result = {"success": False, "error": f"Invalid transfer ID: {transfer_id}"}
            self._log("reject_transfer", {"transfer_id": transfer_id},
                      result, status="error", error=result["error"])
            return result

        old_status = rec["approval_status"]

        if old_status == "Rejected":
            result = {
                "success": False,
                "error": "Duplicate rejection prevented",
                "message": f"Transfer {transfer_id} is already rejected.",
                "current_status": "Rejected",
            }
            self._log("reject_transfer", {"transfer_id": transfer_id},
                      result, status="warning", error="duplicate rejection")
            return result

        if old_status == "Approved":
            result = {
                "success": False,
                "error": "Cannot reject an approved transfer",
                "message": f"Transfer {transfer_id} was already approved. "
                           f"Approval decisions are final.",
                "current_status": "Approved",
            }
            self._log("reject_transfer", {"transfer_id": transfer_id},
                      result, status="warning", error="cannot override approval")
            return result

        updated = self.db.update_approval_status(transfer_id, "Rejected",
                                                 decided_by=decided_by, note=note)
        if updated:
            result = {
                "success": True,
                "transfer_id": transfer_id,
                "previous_status": old_status,
                "new_status": "Rejected",
                "decided_by": decided_by,
                "timestamp": datetime.now().isoformat(),
                "message": f"Transfer {transfer_id} rejected successfully.",
            }
        else:
            result = {
                "success": False,
                "error": "Failed to update rejection status",
                "transfer_id": transfer_id,
            }
        self._log("reject_transfer", {"transfer_id": transfer_id},
                  {"success": result["success"], "new_status": result.get("new_status")})
        return result

    def get_approval_status(self, transfer_id: str) -> dict:
        """Get the current approval status of a transfer."""
        rec = self.db.get_recommendation(transfer_id)
        if rec is None:
            result = {
                "found": False,
                "error": f"Invalid transfer ID: {transfer_id}",
            }
        else:
            result = {
                "found": True,
                "transfer_id": transfer_id,
                "sku": rec["sku"],
                "source_warehouse": rec["source_warehouse"],
                "destination_warehouse": rec["destination_warehouse"],
                "transfer_quantity": rec["transfer_quantity"],
                "approval_status": rec["approval_status"],
                "decision_timestamp": rec["decision_timestamp"],
                "decided_by": rec["decided_by"],
                "decision_note": rec["decision_note"],
            }
        self._log("get_approval_status", {"transfer_id": transfer_id},
                  {"found": result.get("found", False)})
        return result

    def get_approval_summary(self, scenario: str = None) -> dict:
        """Summarize approval statuses."""
        all_recs = self.db.get_all_recommendations(scenario=scenario)
        pending = [r for r in all_recs if r["approval_status"] == "Pending"]
        approved = [r for r in all_recs if r["approval_status"] == "Approved"]
        rejected = [r for r in all_recs if r["approval_status"] == "Rejected"]

        result = {
            "scenario": scenario,
            "total": len(all_recs),
            "pending": len(pending),
            "approved": len(approved),
            "rejected": len(rejected),
            "approved_units": sum(r["transfer_quantity"] for r in approved),
            "approved_transfer_cost": sum(r["transfer_cost_aed"] for r in approved),
            "approved_net_benefit": sum(r["estimated_net_benefit_aed"] for r in approved),
        }
        self._log("get_approval_summary", {"scenario": scenario},
                  {"total": len(all_recs), "pending": len(pending), "approved": len(approved)})
        return result

    def get_audit_trail(self, limit: int = 100) -> list:
        """Get the audit trail of all decisions and actions."""
        return self.db.get_audit_log(limit=limit)
