"""Agent system tests for TradeFlow AI Step 5.

Validates:
- Agents initialize successfully
- Forecasts can be retrieved
- Inventory risks can be analyzed
- Recommendations can be retrieved
- Explanations use actual optimization results
- Approval decisions persist
- Duplicate approvals are prevented
- Invalid transfer IDs are rejected
- Agent errors are handled gracefully
- Switching scenarios does not mix results
- Step 4 discrepancy is documented
"""

import sys
import os
import tempfile

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradeflow_agents import (
    AgentDatabase,
    ForecastingAgent,
    InventoryRiskAgent,
    OptimizationAgent,
    ExplanationAgent,
    ApprovalAgent,
    OrchestratorAgent,
)

DATA_DIR = os.environ.get("TRADEFLOW_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

checks_passed = 0
checks_total = 0


def check(name, condition, detail=""):
    global checks_passed, checks_total
    checks_total += 1
    status = "PASS" if condition else "FAIL"
    if condition:
        checks_passed += 1
    print(f"  [{status}] {name}: {detail}")
    return condition


def safe_cleanup(db_path):
    """Safely remove a DB file, ignoring errors if it's still locked."""
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except (PermissionError, OSError):
        import gc
        gc.collect()
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_agents_initialize():
    """Test that all agents initialize successfully."""
    print("\n--- Test: Agents Initialize ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_tradeflow_agents.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    check("Orchestrator initializes", orch is not None, "OK")
    check("ForecastingAgent initializes", orch.forecast_agent is not None, "OK")
    check("InventoryRiskAgent initializes", orch.inventory_agent is not None, "OK")
    check("OptimizationAgent initializes", orch.optimization_agent is not None, "OK")
    check("ExplanationAgent initializes", orch.explanation_agent is not None, "OK")
    check("ApprovalAgent initializes", orch.approval_agent is not None, "OK")
    check("Database initializes", orch.db is not None, "OK")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_forecast_retrieval():
    """Test that forecasts can be retrieved."""
    print("\n--- Test: Forecast Retrieval ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_forecast.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    # Test specific SKU forecast
    fc = orch.get_demand_forecast("SKU-001", "Dubai")
    check("Forecast found for SKU-001/Dubai", fc.get("found", False),
          f"forecast_30d={fc.get('forecast_30d', 'N/A')}")

    # Test invalid SKU
    fc_invalid = orch.get_demand_forecast("SKU-999", "Dubai")
    check("Invalid SKU returns not found", not fc_invalid.get("found", True),
          fc_invalid.get("error", ""))

    # Test forecast summary
    summary = orch.forecast_agent.summarize_forecast()
    check("Forecast summary has total", summary["total_30d_demand"] > 0,
          f"total={summary['total_30d_demand']:.0f}")
    check("Forecast summary has 60 combos", summary["num_combos"] == 60,
          f"combos={summary['num_combos']}")

    # Test model limitations
    limits = orch.forecast_agent.explain_model_limitations()
    check("Model limitations returned", len(limits["key_limitations"]) > 0,
          f"{len(limits['key_limitations'])} limitations")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_inventory_analysis():
    """Test that inventory risks can be analyzed."""
    print("\n--- Test: Inventory Analysis ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_inventory.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    # Test demonstration scenario
    demo = orch.analyze_inventory("demonstration")
    check("Demo scenario has 60 combos", demo.get("total_combos") == 60,
          f"combos={demo.get('total_combos')}")
    check("Demo scenario has shortages", demo.get("has_shortages", False),
          f"unmet={demo.get('total_unmet_demand', 0):.1f}")
    check("Demo scenario has excess", demo.get("has_excess", False),
          f"excess={demo.get('total_excess_stock', 0):.1f}")
    check("Demo has critical combos", "Critical" in demo.get("risk_counts", {}),
          f"counts={demo.get('risk_counts')}")

    # Test original scenario
    orig = orch.analyze_inventory("original")
    check("Original scenario has 60 combos", orig.get("total_combos") == 60,
          f"combos={orig.get('total_combos')}")
    check("Original scenario has no shortages", not orig.get("has_shortages", True),
          f"unmet={orig.get('total_unmet_demand', 0):.1f}")
    check("Original scenario has excess", orig.get("has_excess", False),
          f"excess={orig.get('total_excess_stock', 0):.1f}")

    # Test comparison
    comparison = orch.compare_scenarios()
    check("Comparison has both scenarios", "original" in comparison and "demonstration" in comparison,
          "OK")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_recommendations():
    """Test that transfer recommendations can be retrieved."""
    print("\n--- Test: Transfer Recommendations ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_recs.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    # Test demonstration scenario (should have recommendations)
    demo_recs = orch.get_transfer_recommendations("demonstration")
    check("Demo has recommendations", demo_recs.get("has_recommendations", False),
          f"num_recs={demo_recs.get('num_recommendations', 0)}")
    check("Demo recommendations > 0", demo_recs.get("num_recommendations", 0) > 0,
          f"{demo_recs.get('num_recommendations', 0)} transfers")
    check("Demo has unmet avoided > 0", demo_recs.get("unmet_avoided", 0) > 0,
          f"{demo_recs.get('unmet_avoided', 0):.1f} units")
    check("Demo has net benefit > 0", demo_recs.get("net_economic_benefit", 0) > 0,
          f"{demo_recs.get('net_economic_benefit', 0):.2f} AED")
    check("Demo transfer quantities are integers",
          all(isinstance(r["transfer_quantity"], int) for r in demo_recs.get("recommendations", [])),
          "OK")
    check("Demo no negative quantities",
          all(r["transfer_quantity"] >= 0 for r in demo_recs.get("recommendations", [])),
          "OK")
    check("Demo no same-warehouse transfers",
          all(r["source_warehouse"] != r["destination_warehouse"] for r in demo_recs.get("recommendations", [])),
          "OK")

    # Test original scenario (should have NO recommendations)
    orig_recs = orch.get_transfer_recommendations("original")
    check("Original has no recommendations", not orig_recs.get("has_recommendations", True),
          f"num_recs={orig_recs.get('num_recommendations', 0)}")
    check("Original has 0 unmet avoided", orig_recs.get("unmet_avoided", -1) == 0,
          f"{orig_recs.get('unmet_avoided', -1)}")

    # Validate source inventory not double-allocated
    validation = orch.optimization_agent.validate_source_inventory(
        demo_recs.get("recommendations", []),
    )
    check("No double allocation of source inventory", validation["valid"],
          "; ".join(validation["issues"]) if validation["issues"] else "all within capacity")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_explanations():
    """Test that explanations use actual optimization results."""
    print("\n--- Test: Explanations ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_explain.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    # Get recommendations first
    opt_result = orch.get_transfer_recommendations("demonstration")
    recs = opt_result.get("recommendations", [])

    if recs:
        # Explain a specific transfer
        first_rec = recs[0]
        tid = first_rec["recommendation_id"]
        explanation = orch.explain_transfer(tid)

        check("Explanation found", explanation.get("found", False),
              f"transfer_id={tid}")
        check("Explanation is deterministic", explanation.get("explanation_type") == "deterministic",
              explanation.get("explanation_type", ""))
        check("Explanation has source reason", len(explanation.get("source_selection_reason", "")) > 10,
              "OK")
        check("Explanation has shortage reduction", len(explanation.get("shortage_reduction_reason", "")) > 10,
              "OK")
        check("Explanation has cost benefit", len(explanation.get("cost_benefit_reason", "")) > 10,
              "OK")
        check("Explanation has assumptions", len(explanation.get("assumptions", "")) > 10,
              "OK")
        check("Explanation has uncertainty", len(explanation.get("uncertainty", "")) > 10,
              "OK")

        # Verify explanation uses actual numbers (not fabricated)
        rec_qty = first_rec["transfer_quantity"]
        exp_qty = explanation.get("transfer_quantity", 0)
        check("Explanation uses actual quantity", rec_qty == exp_qty,
              f"rec={rec_qty}, exp={exp_qty}")

        rec_cost = first_rec["transfer_cost_aed"]
        exp_cost = explanation.get("transfer_cost_aed", -1)
        check("Explanation uses actual cost", abs(rec_cost - exp_cost) < 0.01,
              f"rec={rec_cost}, exp={exp_cost}")

        rec_benefit = first_rec["estimated_net_benefit_aed"]
        exp_benefit = explanation.get("estimated_net_benefit_aed", -999)
        check("Explanation uses actual net benefit", abs(rec_benefit - exp_benefit) < 0.01,
              f"rec={rec_benefit}, exp={exp_benefit}")

        # Test system summary explanation
        sys_summary = orch.explanation_agent.explain_system_summary(opt_result)
        check("System summary is deterministic", sys_summary.get("summary_type") == "deterministic",
              sys_summary.get("summary_type", ""))
        check("System summary has content", len(sys_summary.get("summary", "")) > 50,
              "OK")
    else:
        check("Recommendations exist for explanation test", False, "No recommendations found")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_approval_persistence():
    """Test that approval decisions persist."""
    print("\n--- Test: Approval Persistence ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_approval.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    # First session: get recommendations and approve one
    orch1 = OrchestratorAgent(DATA_DIR, db_path=db_path)
    opt_result = orch1.get_transfer_recommendations("demonstration")
    recs = opt_result.get("recommendations", [])

    if recs:
        first_tid = recs[0]["recommendation_id"]
        second_tid = recs[1]["recommendation_id"] if len(recs) > 1 else None

        # Approve first transfer
        approve_result = orch1.approve_transfer(first_tid, decided_by="test_user")
        check("Approval succeeds", approve_result.get("success", False),
              approve_result.get("message", ""))

        # Reject second transfer if exists
        if second_tid:
            reject_result = orch1.reject_transfer(second_tid, decided_by="test_user")
            check("Rejection succeeds", reject_result.get("success", False),
                  reject_result.get("message", ""))

        orch1.close()

        # Second session: verify decisions persisted
        orch2 = OrchestratorAgent(DATA_DIR, db_path=db_path)
        status1 = orch2.approval_agent.get_approval_status(first_tid)
        check("Approval persists across restart", status1.get("approval_status") == "Approved",
              f"status={status1.get('approval_status')}")

        if second_tid:
            status2 = orch2.approval_agent.get_approval_status(second_tid)
            check("Rejection persists across restart", status2.get("approval_status") == "Rejected",
                  f"status={status2.get('approval_status')}")

        orch2.close()
    else:
        check("Recommendations exist for approval test", False, "No recommendations found")

    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_duplicate_approval_prevention():
    """Test that duplicate approvals are prevented."""
    print("\n--- Test: Duplicate Approval Prevention ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_dup.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)
    opt_result = orch.get_transfer_recommendations("demonstration")
    recs = opt_result.get("recommendations", [])

    if recs:
        tid = recs[0]["recommendation_id"]

        # First approval should succeed
        result1 = orch.approve_transfer(tid)
        check("First approval succeeds", result1.get("success", False), "OK")

        # Second approval should be prevented
        result2 = orch.approve_transfer(tid)
        check("Duplicate approval prevented", not result2.get("success", True),
              result2.get("message", ""))

        # Cannot reject an already-approved transfer
        result3 = orch.reject_transfer(tid)
        check("Cannot reject approved transfer", not result3.get("success", True),
              result3.get("message", ""))
    else:
        check("Recommendations exist for duplicate test", False, "No recommendations found")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_invalid_transfer_id():
    """Test that invalid transfer IDs are rejected."""
    print("\n--- Test: Invalid Transfer ID ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_invalid.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    # Approve invalid ID
    result = orch.approve_transfer("TRF-INVALID-001")
    check("Invalid ID approval rejected", not result.get("success", True),
          result.get("error", ""))

    # Reject invalid ID
    result = orch.reject_transfer("TRF-INVALID-002")
    check("Invalid ID rejection rejected", not result.get("success", True),
          result.get("error", ""))

    # Get status of invalid ID
    status = orch.approval_agent.get_approval_status("TRF-INVALID-003")
    check("Invalid ID status not found", not status.get("found", True),
          status.get("error", ""))

    # Explain invalid ID
    explanation = orch.explain_transfer("TRF-INVALID-004")
    check("Invalid ID explanation rejected", not explanation.get("found", True),
          explanation.get("error", ""))

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_error_handling():
    """Test that agent errors are handled gracefully."""
    print("\n--- Test: Error Handling ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_errors.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    # Invalid scenario
    result = orch.analyze_inventory("invalid_scenario")
    check("Invalid scenario returns error", "error" in result,
          result.get("error", ""))

    result = orch.get_transfer_recommendations("invalid_scenario")
    check("Invalid scenario in optimization returns error", "error" in result,
          result.get("error", ""))

    result = orch.get_system_summary("invalid_scenario")
    check("Invalid scenario in summary returns error", "error" in result,
          result.get("error", ""))

    # Invalid SKU in forecast
    fc = orch.get_demand_forecast("SKU-NONEXIST", "Dubai")
    check("Invalid SKU forecast handled", not fc.get("found", True),
          fc.get("error", ""))

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_scenario_isolation():
    """Test that switching scenarios does not mix results."""
    print("\n--- Test: Scenario Isolation ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_iso.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    # Run demonstration scenario
    demo_opt = orch.get_transfer_recommendations("demonstration")
    demo_recs = demo_opt.get("recommendations", [])
    demo_rec_ids = {r["recommendation_id"] for r in demo_recs}

    # Run original scenario
    orig_opt = orch.get_transfer_recommendations("original")
    orig_recs = orig_opt.get("recommendations", [])
    orig_rec_ids = {r["recommendation_id"] for r in orig_recs}

    # Verify no overlap
    overlap = demo_rec_ids & orig_rec_ids
    check("No ID overlap between scenarios", len(overlap) == 0,
          f"overlap={overlap}" if overlap else "OK")

    # Verify demo has recommendations, original does not
    check("Demo has recommendations", demo_opt.get("has_recommendations", False),
          f"{len(demo_recs)} recs")
    check("Original has no recommendations", not orig_opt.get("has_recommendations", True),
          f"{len(orig_recs)} recs")

    # Verify recommendation IDs contain scenario prefix
    demo_ids_valid = all("DEM" in rid or "demo" in rid.lower() for rid in demo_rec_ids)
    check("Demo recommendation IDs have scenario prefix", demo_ids_valid,
          f"sample: {list(demo_rec_ids)[:2]}" if demo_rec_ids else "no recs")

    # Verify approval system keeps scenarios separate
    demo_approvals = orch.approval_agent.get_all_approvals(scenario="demonstration")
    orig_approvals = orch.approval_agent.get_all_approvals(scenario="original")
    check("Demo approvals > 0", len(demo_approvals) > 0,
          f"{len(demo_approvals)} approvals")
    check("Original approvals == 0", len(orig_approvals) == 0,
          f"{len(orig_approvals)} approvals")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_step4_discrepancy():
    """Test that the Step 4 discrepancy is documented."""
    print("\n--- Test: Step 4 Discrepancy Documentation ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_disc.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)
    opt_result = orch.get_transfer_recommendations("demonstration")

    discrepancy_note = opt_result.get("step4_discrepancy_note")
    check("Discrepancy note exists", discrepancy_note is not None, "OK")
    check("Discrepancy note mentions aggregate", "aggregate" in discrepancy_note.lower(),
          "OK")
    check("Discrepancy note mentions lead time", "lead time" in discrepancy_note.lower(),
          "OK")
    check("Discrepancy note mentions eliminated", "eliminated" in discrepancy_note.lower(),
          "OK")

    # Verify the numbers make sense
    reduction_pct = opt_result.get("unmet_reduction_pct", 0)
    eliminated = opt_result.get("shortages_fully_eliminated", 0)
    shortages_before = opt_result.get("shortages_before", 0)

    check("Reduction pct > 90%", reduction_pct > 90,
          f"{reduction_pct:.1f}%")
    check("Eliminated < total shortages", eliminated < shortages_before,
          f"{eliminated}/{shortages_before}")
    check("Eliminated >= 0", eliminated >= 0,
          f"{eliminated}")

    print(f"\n  Discrepancy note: {discrepancy_note}")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_orchestrator_tools():
    """Test the exposed tool functions."""
    print("\n--- Test: Orchestrator Tool Functions ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_tools.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    # get_demand_forecast
    fc = orch.get_demand_forecast("SKU-001", "Dubai")
    check("get_demand_forecast works", fc.get("found", False), "OK")

    # analyze_inventory
    inv = orch.analyze_inventory("demonstration")
    check("analyze_inventory works", inv.get("total_combos") == 60, "OK")

    # get_transfer_recommendations
    recs = orch.get_transfer_recommendations("demonstration")
    check("get_transfer_recommendations works", recs.get("has_recommendations", False), "OK")

    # explain_transfer (via orchestrator)
    if recs.get("recommendations"):
        tid = recs["recommendations"][0]["recommendation_id"]
        exp = orch.explain_transfer(tid)
        check("explain_transfer works", exp.get("found", False), "OK")

        # approve_transfer
        approve = orch.approve_transfer(tid)
        check("approve_transfer works", approve.get("success", False), "OK")

        # Check it's now approved
        status = orch.approval_agent.get_approval_status(tid)
        check("Approval reflected in status", status.get("approval_status") == "Approved", "OK")

    # get_system_summary
    summary = orch.get_system_summary("demonstration")
    check("get_system_summary works", "scenario" in summary, "OK")
    check("Summary has forecast section", "forecast" in summary, "OK")
    check("Summary has inventory section", "inventory" in summary, "OK")
    check("Summary has optimization section", "optimization" in summary, "OK")
    check("Summary has approval section", "approval" in summary, "OK")

    # Agent log
    log = orch.get_agent_log()
    check("Agent log has entries", len(log) > 0, f"{len(log)} entries")

    # Export agent log
    log_path = os.path.join(tempfile.gettempdir(), "test_agent_log.csv")
    orch.export_agent_log(log_path)
    check("Agent log exported", os.path.exists(log_path), log_path)
    if os.path.exists(log_path):
        os.remove(log_path)

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


def test_audit_trail():
    """Test that the audit trail records decisions."""
    print("\n--- Test: Audit Trail ---")
    db_path = os.path.join(tempfile.gettempdir(), "test_audit.db")
    if os.path.exists(db_path):
        safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)
    opt_result = orch.get_transfer_recommendations("demonstration")
    recs = opt_result.get("recommendations", [])

    if recs:
        tid = recs[0]["recommendation_id"]
        orch.approve_transfer(tid, decided_by="auditor", note="test approval")

        audit = orch.get_audit_trail()
        check("Audit trail has entries", len(audit) > 0, f"{len(audit)} entries")
        check("Audit trail has approval action",
              any("approval" in str(a.get("action", "")).lower() for a in audit),
              "OK")
        check("Audit trail has timestamps",
              all("timestamp" in a for a in audit), "OK")
    else:
        check("Recommendations exist for audit test", False, "No recommendations")

    orch.close()
    if os.path.exists(db_path):
        safe_cleanup(db_path)


if __name__ == "__main__":
    print("=" * 65)
    print("  TradeFlow AI — Agent System Tests (Step 5)")
    print("=" * 65)

    test_agents_initialize()
    test_forecast_retrieval()
    test_inventory_analysis()
    test_recommendations()
    test_explanations()
    test_approval_persistence()
    test_duplicate_approval_prevention()
    test_invalid_transfer_id()
    test_error_handling()
    test_scenario_isolation()
    test_step4_discrepancy()
    test_orchestrator_tools()
    test_audit_trail()

    print()
    print("=" * 65)
    if checks_passed == checks_total:
        print(f"  ALL TESTS PASSED  ({checks_passed}/{checks_total})")
    else:
        print(f"  {checks_passed}/{checks_total} TESTS PASSED, {checks_total - checks_passed} FAILED")
    print("=" * 65)
