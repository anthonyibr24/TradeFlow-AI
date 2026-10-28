"""Dashboard integration tests for TradeFlow AI Step 6.

Verifies:
1. Application imports successfully
2. All pages load
3. Both scenarios work
4. Forecasting data is correct
5. Inventory risk metrics match
6. Optimization recommendations match
7. Agent orchestration works
8. Approval actions persist
9. Rejected recommendations are not counted as approved
10. Approved-plan projections update correctly
11. Scenario switching does not mix approval states
12. No original datasets are overwritten

Also reruns the 86 agent tests.
"""

import sys
import os
import tempfile
import traceback

# Add paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(APP_DIR)
sys.path.insert(0, APP_DIR)
sys.path.insert(0, PARENT_DIR)

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
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


def test_app_imports():
    """Test 1: Application imports successfully."""
    print("\n--- Test: Application Imports ---")
    try:
        from components.styling import inject_css, kpi_card, section_header
        check("components.styling imports", True, "OK")
    except Exception as e:
        check("components.styling imports", False, str(e))

    try:
        from components.charts import inventory_by_warehouse, forecast_line, transfer_network
        check("components.charts imports", True, "OK")
    except Exception as e:
        check("components.charts imports", False, str(e))

    try:
        from components.metrics import load_data, compute_risk_summary
        check("components.metrics imports", True, "OK")
    except Exception as e:
        check("components.metrics imports", False, str(e))

    try:
        from pages import executive_dashboard, demand_forecasting, inventory_intelligence
        check("pages 1-3 imports", True, "OK")
    except Exception as e:
        check("pages 1-3 imports", False, str(e))

    try:
        from pages import transfer_optimization, agent_control_center, approval_center
        check("pages 4-6 imports", True, "OK")
    except Exception as e:
        check("pages 4-6 imports", False, str(e))


def test_data_loading():
    """Test 2: Data loads correctly."""
    print("\n--- Test: Data Loading ---")
    from components.metrics import load_data
    data = load_data(DATA_DIR)

    required_keys = ["products", "warehouses", "sales", "inventory", "scenario_inventory",
                     "inventory_risks", "scenario_risks", "daily_forecast", "forecast_30d",
                     "transfer_routes", "transfer_recs", "opt_summary"]

    for key in required_keys:
        check(f"Data '{key}' loaded", data.get(key) is not None, "OK" if data.get(key) is not None else "MISSING")


def test_both_scenarios():
    """Test 3: Both scenarios work."""
    print("\n--- Test: Both Scenarios ---")
    from components.metrics import load_data, get_scenario_inventory, compute_risk_summary
    data = load_data(DATA_DIR)

    for scenario in ["demonstration", "original"]:
        inv = get_scenario_inventory(data, scenario)
        check(f"{scenario} inventory has 60 combos", len(inv) == 60, f"combos={len(inv)}")

        risk = compute_risk_summary(inv, data["forecast_30d"])
        check(f"{scenario} has risk counts", len(risk["risk_counts"]) > 0,
              f"counts={risk['risk_counts']}")

    # Verify demo has shortages, original doesn't
    demo_inv = get_scenario_inventory(data, "demonstration")
    demo_risk = compute_risk_summary(demo_inv, data["forecast_30d"])
    check("Demo has critical shortages", demo_risk["risk_counts"].get("Critical", 0) > 0,
          f"critical={demo_risk['risk_counts'].get('Critical', 0)}")

    orig_inv = get_scenario_inventory(data, "original")
    orig_risk = compute_risk_summary(orig_inv, data["forecast_30d"])
    check("Original has no critical", orig_risk["risk_counts"].get("Critical", 0) == 0,
          f"critical={orig_risk['risk_counts'].get('Critical', 0)}")


def test_forecasting_data():
    """Test 4: Forecasting charts use correct data."""
    print("\n--- Test: Forecasting Data ---")
    from components.metrics import load_data
    data = load_data(DATA_DIR)

    fc = data["forecast_30d"]
    check("30d forecast has 60 combos", len(fc) == 60, f"combos={len(fc)}")
    check("Forecast has Forecast_30d column", "Forecast_30d" in fc.columns, "OK")
    check("Forecast has uncertainty bounds", "Lower_Bound" in fc.columns and "Upper_Bound" in fc.columns, "OK")

    daily = data["daily_forecast"]
    check("Daily forecast has 1800 rows", len(daily) == 1800, f"rows={len(daily)}")

    # Check specific SKU forecast matches
    sku001 = fc[(fc["SKU"] == "SKU-001") & (fc["Warehouse"] == "Dubai")]
    if not sku001.empty:
        check("SKU-001/Dubai forecast exists", True, f"forecast={sku001.iloc[0]['Forecast_30d']:.0f}")
    else:
        check("SKU-001/Dubai forecast exists", False, "Not found")


def test_inventory_risk_metrics():
    """Test 5: Inventory risk metrics match existing results."""
    print("\n--- Test: Inventory Risk Metrics ---")
    from components.metrics import load_data, get_scenario_inventory, compute_risk_summary
    data = load_data(DATA_DIR)

    inv = get_scenario_inventory(data, "demonstration")
    risk = compute_risk_summary(inv, data["forecast_30d"])

    check("Demo has 60 combos", risk["risk_counts"].get("Critical", 0) + risk["risk_counts"].get("Warning", 0) +
          risk["risk_counts"].get("Excess", 0) + risk["risk_counts"].get("Healthy", 0) == 60,
          f"counts={risk['risk_counts']}")
    check("Demo has shortages", risk["total_unmet"] > 0, f"unmet={risk['total_unmet']:.0f}")
    check("Demo has excess", risk["total_excess"] > 0, f"excess={risk['total_excess']:.0f}")
    check("Demo has 3 warehouses", len(risk["by_warehouse"]) == 3,
          f"warehouses={list(risk['by_warehouse'].keys())}")


def test_optimization_recommendations():
    """Test 6: Optimization recommendations match actual solver outputs."""
    print("\n--- Test: Optimization Recommendations ---")
    from components.metrics import load_data, get_opt_summary
    data = load_data(DATA_DIR)

    opt = get_opt_summary(data)
    check("Has 28 recommendations", int(opt.get("Number of recommended transfers", 0)) == 28,
          f"num={opt.get('Number of recommended transfers', 0)}")
    check("Total units is 1108", int(opt.get("Total units recommended", 0)) == 1108,
          f"units={opt.get('Total units recommended', 0)}")
    check("Transfer cost is 2021.50", abs(float(opt.get("Total transfer cost", 0)) - 2021.50) < 1,
          f"cost={opt.get('Total transfer cost', 0)}")
    check("Unmet before is ~1119.7", abs(float(opt.get("Unmet demand before transfers", 0)) - 1119.7) < 2,
          f"before={opt.get('Unmet demand before transfers', 0)}")
    check("Net benefit is ~44817", abs(float(opt.get("Net economic benefit", 0)) - 44817.17) < 50,
          f"benefit={opt.get('Net economic benefit', 0)}")

    recs = data["transfer_recs"]
    check("All recs have Pending status", (recs["Approval_Status"] == "Pending").all(), "OK")
    check("All quantities are integers", recs["Transfer_Quantity"].dtype in ["int64", "int32"],
          f"dtype={recs['Transfer_Quantity'].dtype}")
    check("No negative quantities", (recs["Transfer_Quantity"] >= 0).all(), "OK")
    check("No same-warehouse transfers", (recs["Source_Warehouse"] != recs["Destination_Warehouse"]).all(), "OK")


def test_agent_orchestration():
    """Test 7: Agent orchestration works."""
    print("\n--- Test: Agent Orchestration ---")
    from tradeflow_agents import OrchestratorAgent

    db_path = os.path.join(tempfile.gettempdir(), "test_dashboard_orch.db")
    safe_cleanup(db_path)
    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)

    check("Orchestrator initializes", orch is not None, "OK")
    check("ForecastAgent initializes", orch.forecast_agent is not None, "OK")
    check("InventoryAgent initializes", orch.inventory_agent is not None, "OK")
    check("OptimizationAgent initializes", orch.optimization_agent is not None, "OK")
    check("ExplanationAgent initializes", orch.explanation_agent is not None, "OK")
    check("ApprovalAgent initializes", orch.approval_agent is not None, "OK")

    # Test individual agent calls
    fc = orch.get_demand_forecast("SKU-001", "Dubai")
    check("get_demand_forecast works", fc.get("found", False), "OK")

    inv = orch.analyze_inventory("demonstration")
    check("analyze_inventory works", inv.get("total_combos") == 60, "OK")

    opt = orch.get_transfer_recommendations("demonstration")
    check("get_transfer_recommendations works", opt.get("has_recommendations", False),
          f"num_recs={opt.get('num_recommendations', 0)}")

    summary = orch.get_system_summary("demonstration")
    check("get_system_summary works", "scenario" in summary, "OK")

    orch.close()
    safe_cleanup(db_path)


def test_approval_persistence():
    """Test 8: Approval actions persist."""
    print("\n--- Test: Approval Persistence ---")
    from tradeflow_agents import OrchestratorAgent

    db_path = os.path.join(tempfile.gettempdir(), "test_dashboard_approval.db")
    safe_cleanup(db_path)

    orch1 = OrchestratorAgent(DATA_DIR, db_path=db_path)
    opt = orch1.get_transfer_recommendations("demonstration")
    recs = opt.get("recommendations", [])

    if recs:
        tid = recs[0]["recommendation_id"]
        result = orch1.approve_transfer(tid, decided_by="test")
        check("Approval succeeds", result.get("success", False), result.get("message", ""))
        orch1.close()

        # New session
        orch2 = OrchestratorAgent(DATA_DIR, db_path=db_path)
        status = orch2.approval_agent.get_approval_status(tid)
        check("Approval persists", status.get("approval_status") == "Approved",
              f"status={status.get('approval_status')}")
        orch2.close()

    safe_cleanup(db_path)


def test_rejected_not_approved():
    """Test 9: Rejected recommendations are not counted as approved."""
    print("\n--- Test: Rejected Not Approved ---")
    from tradeflow_agents import OrchestratorAgent

    db_path = os.path.join(tempfile.gettempdir(), "test_dashboard_reject.db")
    safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)
    opt = orch.get_transfer_recommendations("demonstration")
    recs = opt.get("recommendations", [])

    if recs:
        tid = recs[0]["recommendation_id"]
        orch.reject_transfer(tid, decided_by="test")

        summary = orch.approval_agent.get_approval_summary(scenario="demonstration")
        check("Rejected count is 1", summary["rejected"] == 1, f"rejected={summary['rejected']}")
        check("Approved count is 0", summary["approved"] == 0, f"approved={summary['approved']}")
        check("Approved units is 0", summary["approved_units"] == 0, f"units={summary['approved_units']}")

    orch.close()
    safe_cleanup(db_path)


def test_approved_plan_tracking():
    """Test 10: Approved-plan projections update correctly."""
    print("\n--- Test: Approved Plan Tracking ---")
    from tradeflow_agents import OrchestratorAgent
    from components.metrics import compute_approved_plan_impact

    db_path = os.path.join(tempfile.gettempdir(), "test_dashboard_plan.db")
    safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)
    opt = orch.get_transfer_recommendations("demonstration")
    recs = opt.get("recommendations", [])

    if recs:
        # Approve first 3
        for r in recs[:3]:
            orch.approve_transfer(r["recommendation_id"])

        all_recs = orch.approval_agent.get_all_approvals(scenario="demonstration")
        plan = compute_approved_plan_impact(orch, "demonstration", all_recs)

        check("3 approved", plan["approved_count"] == 3, f"approved={plan['approved_count']}")
        check("Approved benefit > 0", plan["approved_benefit"] > 0, f"benefit={plan['approved_benefit']:.0f}")
        check("Total proposed > approved", plan["total_proposed_benefit"] > plan["approved_benefit"],
              f"total={plan['total_proposed_benefit']:.0f} > approved={plan['approved_benefit']:.0f}")

    orch.close()
    safe_cleanup(db_path)


def test_scenario_isolation():
    """Test 11: Scenario switching does not mix approval states."""
    print("\n--- Test: Scenario Isolation ---")
    from tradeflow_agents import OrchestratorAgent

    db_path = os.path.join(tempfile.gettempdir(), "test_dashboard_iso.db")
    safe_cleanup(db_path)

    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)
    orch.get_transfer_recommendations("demonstration")
    orch.get_transfer_recommendations("original")

    demo_approvals = orch.approval_agent.get_all_approvals(scenario="demonstration")
    orig_approvals = orch.approval_agent.get_all_approvals(scenario="original")

    check("Demo has approvals", len(demo_approvals) > 0, f"count={len(demo_approvals)}")
    check("Original has no approvals", len(orig_approvals) == 0, f"count={len(orig_approvals)}")

    # No overlap in IDs
    demo_ids = {r["recommendation_id"] for r in demo_approvals}
    orig_ids = {r["recommendation_id"] for r in orig_approvals}
    overlap = demo_ids & orig_ids
    check("No ID overlap", len(overlap) == 0, "OK")

    orch.close()
    safe_cleanup(db_path)


def test_no_data_modification():
    """Test 12: No original datasets are overwritten."""
    print("\n--- Test: No Data Modification ---")
    import pandas as pd

    # Record file sizes before
    files_to_check = ["products.csv", "inventory.csv", "scenario_inventory.csv",
                      "improved_forecast_30d.csv", "transfer_recommendations.csv",
                      "transfer_optimization_summary.csv"]

    sizes_before = {}
    for f in files_to_check:
        path = os.path.join(DATA_DIR, f)
        if os.path.exists(path):
            sizes_before[f] = os.path.getsize(path)

    # Run orchestrator (which might modify things)
    from tradeflow_agents import OrchestratorAgent
    db_path = os.path.join(tempfile.gettempdir(), "test_dashboard_nomod.db")
    safe_cleanup(db_path)
    orch = OrchestratorAgent(DATA_DIR, db_path=db_path)
    orch.get_transfer_recommendations("demonstration")
    orch.close()
    safe_cleanup(db_path)

    # Check sizes haven't changed
    all_ok = True
    for f, size_before in sizes_before.items():
        path = os.path.join(DATA_DIR, f)
        size_after = os.path.getsize(path)
        if size_before != size_after:
            check(f"{f} not modified", False, f"before={size_before} after={size_after}")
            all_ok = False

    if all_ok:
        check("All original datasets preserved", True, "OK")


def test_agent_tests():
    """Rerun the 86 agent system tests."""
    print("\n--- Test: Agent System Tests (86 checks) ---")
    import subprocess
    test_path = os.path.join(APP_DIR, "agent_system_tests.py")
    result = subprocess.run([sys.executable, test_path],
                           capture_output=True, text=True, timeout=300)
    check("Agent tests all pass", result.returncode == 0 and "ALL TESTS PASSED" in result.stdout,
          "See agent_system_tests.py output")


if __name__ == "__main__":
    print("=" * 65)
    print("  TradeFlow AI — Dashboard Integration Tests (Step 6)")
    print("=" * 65)

    test_app_imports()
    test_data_loading()
    test_both_scenarios()
    test_forecasting_data()
    test_inventory_risk_metrics()
    test_optimization_recommendations()
    test_agent_orchestration()
    test_approval_persistence()
    test_rejected_not_approved()
    test_approved_plan_tracking()
    test_scenario_isolation()
    test_no_data_modification()
    test_agent_tests()

    print()
    print("=" * 65)
    if checks_passed == checks_total:
        print(f"  ALL TESTS PASSED  ({checks_passed}/{checks_total})")
    else:
        print(f"  {checks_passed}/{checks_total} TESTS PASSED, {checks_total - checks_passed} FAILED")
    print("=" * 65)
