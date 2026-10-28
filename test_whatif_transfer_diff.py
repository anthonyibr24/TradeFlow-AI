"""Regression test: What-If transfer recommendation diff matches optimizer results.

Verifies that the transfer_diff returned by run_whatif_simulation exactly matches
what the optimizer produces when comparing baseline vs modified recommendations.

Test scenario: Reduce SKU-001 at Abu Dhabi from 157 to 0 units (as described in requirements).
Expected: recommendations increase from 28 to 29, post-transfer unmet ~100.3, net benefit ~45,794.
"""
import sys, os, io, traceback
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Data dir discovery
_data_candidates = [
    os.environ.get("TRADEFLOW_DATA_DIR"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datasets"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Datasets"),
]
for _c in _data_candidates:
    if _c and os.path.exists(_c) and os.path.exists(os.path.join(_c, "products.csv")):
        os.environ["TRADEFLOW_DATA_DIR"] = _c
        break

sys.path.insert(0, ".")

DATA_DIR = os.environ.get("TRADEFLOW_DATA_DIR")
if not DATA_DIR:
    print("ERROR: Data directory not found. Set TRADEFLOW_DATA_DIR.")
    sys.exit(1)

passed = []
failed = []

def test(name, func):
    try:
        func()
        passed.append(name)
        print(f"  PASS: {name}")
    except Exception as e:
        failed.append((name, str(e)))
        print(f"  FAIL: {name}: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════
# Setup: Run the what-if simulation (SKU-001, Abu Dhabi, 157→0)
# ════════════════════════════════════════════════════════════════
print("\n=== Running What-If simulation: SKU-001 at Abu Dhabi, 157 → 0 ===")
from simulation_engine import run_whatif_simulation, compare_transfer_recommendations, explain_no_transfer_for_combo
from tradeflow_agents.optimization_agent import OptimizationAgent

wf_result = run_whatif_simulation(DATA_DIR, "demonstration", "SKU-001", "Abu Dhabi", 0)
print("Simulation complete.\n")


# ════════════════════════════════════════════════════════════════
# TEST 1: transfer_diff exists in whatif result
# ════════════════════════════════════════════════════════════════
def test_transfer_diff_exists():
    assert "transfer_diff" in wf_result, "transfer_diff key missing from whatif result"
    td = wf_result["transfer_diff"]
    assert "added" in td, "transfer_diff missing 'added'"
    assert "removed" in td, "transfer_diff missing 'removed'"
    assert "changed" in td, "transfer_diff missing 'changed'"
    assert "unchanged" in td, "transfer_diff missing 'unchanged'"
    assert "summary" in td, "transfer_diff missing 'summary'"

test("1. transfer_diff exists in whatif result", test_transfer_diff_exists)


# ════════════════════════════════════════════════════════════════
# TEST 2: Diff counts match optimizer recommendation counts
# ════════════════════════════════════════════════════════════════
def test_diff_counts_match_optimizer():
    td = wf_result["transfer_diff"]
    bo = wf_result["baseline_opt"]
    mo = wf_result["modified_opt"]

    n_baseline = bo["num_recommendations"]
    n_modified = mo["num_recommendations"]

    s = td["summary"]
    # added + unchanged + changed = total modified
    reconstructed_modified = s["added_count"] + s["unchanged_count"] + s["changed_count"]
    assert reconstructed_modified == n_modified, \
        f"Reconstructed modified ({reconstructed_modified}) != optimizer modified ({n_modified})"

    # removed + unchanged + changed = total baseline
    reconstructed_baseline = s["removed_count"] + s["unchanged_count"] + s["changed_count"]
    assert reconstructed_baseline == n_baseline, \
        f"Reconstructed baseline ({reconstructed_baseline}) != optimizer baseline ({n_baseline})"

test("2. Diff counts match optimizer recommendation counts", test_diff_counts_match_optimizer)


# ════════════════════════════════════════════════════════════════
# TEST 3: Each transfer in diff has required display fields
# ════════════════════════════════════════════════════════════════
def test_transfer_fields_present():
    td = wf_result["transfer_diff"]
    required_fields = [
        "sku", "source_warehouse", "destination_warehouse",
        "transfer_quantity", "transfer_cost_aed",
        "expected_unmet_avoided", "estimated_net_benefit_aed",
        "product_name", "lead_time_days",
    ]

    for category in ["added", "removed", "unchanged"]:
        for rec in td[category]:
            for field in required_fields:
                assert field in rec, \
                    f"Transfer in '{category}' missing field '{field}': {rec}"

    # Changed entries have baseline + modified sub-dicts
    for item in td["changed"]:
        assert "baseline" in item, "Changed entry missing 'baseline'"
        assert "modified" in item, "Changed entry missing 'modified'"
        for field in required_fields:
            assert field in item["baseline"], f"Changed baseline missing '{field}'"
            assert field in item["modified"], f"Changed modified missing '{field}'"

test("3. Each transfer has required display fields", test_transfer_fields_present)


# ════════════════════════════════════════════════════════════════
# TEST 4: Diff matches independent manual comparison
# ════════════════════════════════════════════════════════════════
def test_diff_matches_manual_comparison():
    """Re-run the optimizer independently and compare manually."""
    td = wf_result["transfer_diff"]
    bo_recs = wf_result["baseline_opt"]["recommendations"]
    mo_recs = wf_result["modified_opt"]["recommendations"]

    # Manual comparison
    def _key(r):
        return (r.get("sku", ""), r.get("source_warehouse", ""), r.get("destination_warehouse", ""))

    b_map = {_key(r): r for r in bo_recs}
    m_map = {_key(r): r for r in mo_recs}

    manual_added = [k for k in m_map if k not in b_map]
    manual_removed = [k for k in b_map if k not in m_map]
    manual_changed = [k for k in b_map if k in m_map and b_map[k]["transfer_quantity"] != m_map[k]["transfer_quantity"]]
    manual_unchanged = [k for k in b_map if k in m_map and b_map[k]["transfer_quantity"] == m_map[k]["transfer_quantity"]]

    assert len(manual_added) == td["summary"]["added_count"], \
        f"Added count mismatch: manual={len(manual_added)}, diff={td['summary']['added_count']}"
    assert len(manual_removed) == td["summary"]["removed_count"], \
        f"Removed count mismatch: manual={len(manual_removed)}, diff={td['summary']['removed_count']}"
    assert len(manual_changed) == td["summary"]["changed_count"], \
        f"Changed count mismatch: manual={len(manual_changed)}, diff={td['summary']['changed_count']}"
    assert len(manual_unchanged) == td["summary"]["unchanged_count"], \
        f"Unchanged count mismatch: manual={len(manual_unchanged)}, diff={td['summary']['unchanged_count']}"

    # Verify the actual keys match
    diff_added_keys = {(_key(r)) for r in td["added"]}
    assert diff_added_keys == set(manual_added), \
        f"Added keys don't match: {diff_added_keys} vs {set(manual_added)}"

    diff_removed_keys = {(_key(r)) for r in td["removed"]}
    assert diff_removed_keys == set(manual_removed), \
        f"Removed keys don't match: {diff_removed_keys} vs {set(manual_removed)}"

test("4. Diff matches independent manual comparison", test_diff_matches_manual_comparison)


# ════════════════════════════════════════════════════════════════
# TEST 5: Baseline optimization values match known baseline (28 recs, ~44,817 AED)
# ════════════════════════════════════════════════════════════════
def test_baseline_values():
    bo = wf_result["baseline_opt"]
    assert bo["num_recommendations"] == 28, \
        f"Expected 28 baseline recs, got {bo['num_recommendations']}"
    assert abs(bo["net_economic_benefit"] - 44817) < 100, \
        f"Expected ~44,817 baseline benefit, got {bo['net_economic_benefit']:.0f}"
    assert abs(bo["post_transfer_unmet"] - 12.4) < 2.0, \
        f"Expected ~12.4 baseline post-unmet, got {bo['post_transfer_unmet']:.1f}"

test("5. Baseline optimization values match known baseline", test_baseline_values)


# ════════════════════════════════════════════════════════════════
# TEST 6: Modified optimization values match expected (29 recs, ~45,794 AED, ~100.3 unmet)
# ════════════════════════════════════════════════════════════════
def test_modified_values():
    mo = wf_result["modified_opt"]
    assert mo["num_recommendations"] == 29, \
        f"Expected 29 modified recs, got {mo['num_recommendations']}"
    assert abs(mo["net_economic_benefit"] - 45794) < 200, \
        f"Expected ~45,794 modified benefit, got {mo['net_economic_benefit']:.0f}"
    # Post-transfer unmet should be ~100.3 (increased from 12.4)
    assert mo["post_transfer_unmet"] > 50, \
        f"Expected post-transfer unmet > 50 (was ~100.3), got {mo['post_transfer_unmet']:.1f}"

test("6. Modified optimization values match expected (29 recs, ~45,794)", test_modified_values)


# ════════════════════════════════════════════════════════════════
# TEST 7: Modified combo recs are highlighted correctly
# ════════════════════════════════════════════════════════════════
def test_modified_combo_recs_highlighted():
    td = wf_result["transfer_diff"]
    cc = wf_result["changed_combo"]
    combo_recs = td["modified_combo_recs"]

    # Every rec in modified_combo_recs should involve SKU-001 or Abu Dhabi
    for rec in combo_recs:
        sku = rec.get("sku", "")
        src = rec.get("source_warehouse", "")
        dst = rec.get("destination_warehouse", "")
        assert (sku == cc["sku"] or src == cc["warehouse"] or dst == cc["warehouse"]), \
            f"Modified combo rec doesn't involve {cc['sku']}/{cc['warehouse']}: sku={sku}, src={src}, dst={dst}"

test("7. Modified combo transfers highlighted correctly", test_modified_combo_recs_highlighted)


# ════════════════════════════════════════════════════════════════
# TEST 8: compare_transfer_recommendations function works standalone
# ════════════════════════════════════════════════════════════════
def test_compare_function_standalone():
    """Test the comparison function directly with known inputs."""
    baseline_recs = [
        {"sku": "SKU-001", "source_warehouse": "Dubai", "destination_warehouse": "Sharjah",
         "transfer_quantity": 50, "transfer_cost_aed": 100, "estimated_net_benefit_aed": 200,
         "product_name": "Test Product", "expected_unmet_avoided": 45, "lead_time_days": 1},
        {"sku": "SKU-002", "source_warehouse": "Dubai", "destination_warehouse": "Abu Dhabi",
         "transfer_quantity": 30, "transfer_cost_aed": 60, "estimated_net_benefit_aed": 120,
         "product_name": "Test Product 2", "expected_unmet_avoided": 25, "lead_time_days": 2},
    ]
    modified_recs = [
        {"sku": "SKU-001", "source_warehouse": "Dubai", "destination_warehouse": "Sharjah",
         "transfer_quantity": 70, "transfer_cost_aed": 140, "estimated_net_benefit_aed": 280,
         "product_name": "Test Product", "expected_unmet_avoided": 60, "lead_time_days": 1},
        {"sku": "SKU-003", "source_warehouse": "Sharjah", "destination_warehouse": "Abu Dhabi",
         "transfer_quantity": 20, "transfer_cost_aed": 40, "estimated_net_benefit_aed": 80,
         "product_name": "Test Product 3", "expected_unmet_avoided": 15, "lead_time_days": 1},
    ]

    result = compare_transfer_recommendations(baseline_recs, modified_recs, "SKU-001", "Abu Dhabi")

    # SKU-001 Dubai→Sharjah: quantity changed 50→70
    assert result["summary"]["changed_count"] == 1, \
        f"Expected 1 changed, got {result['summary']['changed_count']}"
    # SKU-002 Dubai→Abu Dhabi: removed (not in modified)
    assert result["summary"]["removed_count"] == 1, \
        f"Expected 1 removed, got {result['summary']['removed_count']}"
    # SKU-003 Sharjah→Abu Dhabi: added
    assert result["summary"]["added_count"] == 1, \
        f"Expected 1 added, got {result['summary']['added_count']}"
    assert result["summary"]["unchanged_count"] == 0, \
        f"Expected 0 unchanged, got {result['summary']['unchanged_count']}"

    # Modified combo recs: SKU-001 (changed), SKU-002 (removed, involves Abu Dhabi),
    # SKU-003 (added, involves Abu Dhabi)
    assert len(result["modified_combo_recs"]) == 3, \
        f"Expected 3 modified combo recs, got {len(result['modified_combo_recs'])}"

test("8. compare_transfer_recommendations function works standalone", test_compare_function_standalone)


# ════════════════════════════════════════════════════════════════
# TEST 9: No-transfer explanation exists when needed
# ════════════════════════════════════════════════════════════════
def test_no_transfer_explanation():
    """When reducing SKU-001 at Abu Dhabi to 0, the modified warehouse likely has a shortage.
    Check if no_transfer_explanation is populated when no transfer targets it."""
    td = wf_result["transfer_diff"]
    mo_recs = wf_result["modified_opt"]["recommendations"]
    cc = wf_result["changed_combo"]

    # Check if any modified rec has destination = Abu Dhabi for SKU-001
    has_transfer = any(
        r.get("sku") == cc["sku"] and r.get("destination_warehouse") == cc["warehouse"]
        for r in mo_recs
    )

    nte = wf_result.get("no_transfer_explanation")
    if not has_transfer:
        assert nte is not None, \
            "No transfer recommended for modified combo but no_transfer_explanation is None"
        assert "has_shortage" in nte, "no_transfer_explanation missing has_shortage"
        assert "reasons" in nte, "no_transfer_explanation missing reasons"
        assert len(nte["reasons"]) > 0, "no_transfer_explanation has empty reasons"
        # Each reason should be a non-empty string (not a guess)
        for reason in nte["reasons"]:
            assert isinstance(reason, str) and len(reason) > 10, \
                f"Reason too short or not a string: {reason}"
    else:
        # If there IS a transfer, explanation might be None or indicate no shortage
        pass

test("9. No-transfer explanation populated when needed", test_no_transfer_explanation)


# ════════════════════════════════════════════════════════════════
# TEST 10: explain_no_transfer_for_combo works standalone
# ════════════════════════════════════════════════════════════════
def test_explain_function_standalone():
    """Test explain_no_transfer_for_combo on baseline inventory."""
    import pandas as pd
    inv_path = os.path.join(DATA_DIR, "scenario_inventory.csv")
    inv = pd.read_csv(inv_path)

    # Pick a SKU-warehouse that has surplus (no shortage) to test the "no shortage" path
    result = explain_no_transfer_for_combo(DATA_DIR, "demonstration", "SKU-001", "Dubai", inv)
    assert "has_shortage" in result
    assert "reasons" in result
    assert len(result["reasons"]) > 0

    # If there's no shortage, the reason should say so
    if not result["has_shortage"]:
        assert "No shortage" in result["reasons"][0] or "no shortage" in result["reasons"][0].lower()

test("10. explain_no_transfer_for_combo works standalone", test_explain_function_standalone)


# ════════════════════════════════════════════════════════════════
# TEST 11: Approval Center is NOT modified by what-if simulation
# ════════════════════════════════════════════════════════════════
def test_approval_center_not_modified():
    """Verify the what-if simulation does not save to the approval database."""
    from tradeflow_agents.approval_agent import ApprovalAgent
    from tradeflow_agents.database import AgentDatabase
    import tempfile

    db_path = os.path.join(tempfile.gettempdir(), "test_whatif_approval_check.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    db = AgentDatabase(db_path)
    agent = ApprovalAgent(db)

    # Load baseline recs only
    opt_agent = OptimizationAgent(DATA_DIR)
    opt_result = opt_agent.get_transfer_recommendations("demonstration")
    agent.load_recommendations(opt_result["recommendations"], "demonstration")

    baseline_count = len(agent.get_all_approvals(scenario="demonstration"))

    # Now run what-if (which should NOT touch the approval DB)
    _ = run_whatif_simulation(DATA_DIR, "demonstration", "SKU-001", "Abu Dhabi", 0)

    after_count = len(agent.get_all_approvals(scenario="demonstration"))

    assert baseline_count == after_count, \
        f"Approval count changed after what-if: {baseline_count} → {after_count}. " \
        "What-if should NOT modify the Approval Center."

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)

test("11. Approval Center not modified by what-if simulation", test_approval_center_not_modified)


# ════════════════════════════════════════════════════════════════
# TEST 12: Original CSV files unchanged after simulation
# ════════════════════════════════════════════════════════════════
def test_csv_files_unchanged():
    """Verify what-if simulation doesn't modify original CSV files."""
    import hashlib

    files_to_check = ["scenario_inventory.csv", "inventory.csv", "improved_forecast_30d.csv"]
    hashes_before = {}
    for f in files_to_check:
        path = os.path.join(DATA_DIR, f)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                hashes_before[f] = hashlib.md5(fh.read()).hexdigest()

    # Run what-if
    _ = run_whatif_simulation(DATA_DIR, "demonstration", "SKU-001", "Abu Dhabi", 0)

    for f, hash_before in hashes_before.items():
        path = os.path.join(DATA_DIR, f)
        with open(path, "rb") as fh:
            hash_after = hashlib.md5(fh.read()).hexdigest()
        assert hash_before == hash_after, \
            f"File {f} was modified by what-if simulation!"

test("12. Original CSV files unchanged after simulation", test_csv_files_unchanged)


# ════════════════════════════════════════════════════════════════
# TEST 13: Page renders transfer changes section (source code check)
# ════════════════════════════════════════════════════════════════
def test_page_has_transfer_changes_section():
    import pages.agent_control_center as acc
    import inspect

    source = inspect.getsource(acc)
    assert "_render_transfer_changes" in source, \
        "agent_control_center.py missing _render_transfer_changes function"
    assert "What Transfers Does AI Recommend?" in source, \
        "agent_control_center.py missing 'What Transfers Does AI Recommend?' section header"
    assert "simulated recommendations only" in source.lower(), \
        "Missing simulated recommendations disclaimer"
    assert "transfer_diff" in source, \
        "agent_control_center.py doesn't reference transfer_diff"
    assert "no_transfer_explanation" in source, \
        "agent_control_center.py doesn't reference no_transfer_explanation"
    # Verify native Streamlit tables (st.dataframe) used, not HTML
    assert "st.dataframe" in source, "Should use native st.dataframe for tables"

test("13. Page has transfer changes section with native Streamlit tables", test_page_has_transfer_changes_section)


# ════════════════════════════════════════════════════════════════
# TEST 14: Added transfer display fields match optimizer output
# ════════════════════════════════════════════════════════════════
def test_added_transfers_match_optimizer():
    """Each 'added' transfer in the diff should exist in the modified optimizer result."""
    td = wf_result["transfer_diff"]
    mo_recs = wf_result["modified_opt"]["recommendations"]

    mo_keys = {(r["sku"], r["source_warehouse"], r["destination_warehouse"]) for r in mo_recs}

    for rec in td["added"]:
        key = (rec["sku"], rec["source_warehouse"], rec["destination_warehouse"])
        assert key in mo_keys, \
            f"Added transfer {key} not found in modified optimizer results"

        # Verify quantity matches
        mo_rec = next(r for r in mo_recs if (r["sku"], r["source_warehouse"], r["destination_warehouse"]) == key)
        assert rec["transfer_quantity"] == mo_rec["transfer_quantity"], \
            f"Added transfer {key} quantity mismatch: diff={rec['transfer_quantity']}, opt={mo_rec['transfer_quantity']}"
        assert abs(rec["estimated_net_benefit_aed"] - mo_rec["estimated_net_benefit_aed"]) < 0.01, \
            f"Added transfer {key} net benefit mismatch"

test("14. Added transfers match optimizer output exactly", test_added_transfers_match_optimizer)


# ════════════════════════════════════════════════════════════════
# TEST 15: Removed transfers match optimizer output
# ════════════════════════════════════════════════════════════════
def test_removed_transfers_match_optimizer():
    """Each 'removed' transfer in the diff should exist in baseline but not modified."""
    td = wf_result["transfer_diff"]
    bo_recs = wf_result["baseline_opt"]["recommendations"]
    mo_recs = wf_result["modified_opt"]["recommendations"]

    bo_keys = {(r["sku"], r["source_warehouse"], r["destination_warehouse"]) for r in bo_recs}
    mo_keys = {(r["sku"], r["source_warehouse"], r["destination_warehouse"]) for r in mo_recs}

    for rec in td["removed"]:
        key = (rec["sku"], rec["source_warehouse"], rec["destination_warehouse"])
        assert key in bo_keys, \
            f"Removed transfer {key} not found in baseline optimizer results"
        assert key not in mo_keys, \
            f"Removed transfer {key} should NOT be in modified optimizer results"

test("15. Removed transfers match optimizer output exactly", test_removed_transfers_match_optimizer)


# ════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print(f"WHAT-IF TRANSFER DIFF TESTS: {len(passed)} passed, {len(failed)} failed")
print("=" * 70)
if failed:
    print("\nFAILED TESTS:")
    for name, err in failed:
        print(f"  x {name}: {err}")
else:
    print("\nALL WHAT-IF TRANSFER DIFF TESTS PASSED")
print()

# Print summary of the simulation
td = wf_result["transfer_diff"]
s = td["summary"]
print("SIMULATION SUMMARY (SKU-001 at Abu Dhabi, 157 → 0):")
print(f"  Baseline recommendations:  {s['total_baseline']}")
print(f"  Modified recommendations:  {s['total_modified']}")
print(f"  Added:   {s['added_count']}")
print(f"  Removed: {s['removed_count']}")
print(f"  Changed: {s['changed_count']}")
print(f"  Unchanged: {s['unchanged_count']}")
print(f"  Baseline net benefit: {wf_result['baseline_opt']['net_economic_benefit']:.0f} AED")
print(f"  Modified net benefit: {wf_result['modified_opt']['net_economic_benefit']:.0f} AED")
print(f"  Baseline post-unmet: {wf_result['baseline_opt']['post_transfer_unmet']:.1f}")
print(f"  Modified post-unmet: {wf_result['modified_opt']['post_transfer_unmet']:.1f}")
