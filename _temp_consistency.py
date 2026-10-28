"""Verify cross-page value consistency."""
import os, sys
os.environ['TRADEFLOW_DATA_DIR'] = r'C:\Users\antho\Desktop\CUD\Semester 7\Hackathon\Problem statement\Datasets'
sys.path.insert(0, '.')

import pandas as pd
from components.metrics import load_data, compute_risk_summary, get_opt_summary, get_scenario_inventory
from tradeflow_agents.optimization_agent import OptimizationAgent

DATA_DIR = os.environ['TRADEFLOW_DATA_DIR']
data = load_data(DATA_DIR)
inv = get_scenario_inventory(data, "demonstration")
fc30 = data["forecast_30d"]

# 1. Forecast demand ~6,385
risk = compute_risk_summary(inv, fc30)
print(f"Forecast demand (compute_risk_summary): {risk['total_forecast']:.1f}")

# 2. Total inventory ~10,936
print(f"Total available inventory: {risk['total_available']}")

# 3-4. Transfer recommendations: 28, units: 1,108
agent = OptimizationAgent(DATA_DIR)
opt = agent.get_transfer_recommendations("demonstration")
print(f"Transfer recommendations: {opt['num_recommendations']}")
print(f"Units transferred: {opt['total_units_recommended']}")

# 5. Transfer cost ~2,021.50
print(f"Transfer cost: {opt['total_transfer_cost']:.2f}")

# 6. Projected net benefit ~44,817.17
print(f"Net economic benefit: {opt['net_economic_benefit']:.2f}")

# 7. Dynamic unmet before ~1,119.7
print(f"Dynamic unmet before optimization: {opt['baseline_unmet']:.1f}")

# 8. Dynamic unmet after ~12.4
print(f"Dynamic unmet after optimization: {opt['post_transfer_unmet']:.1f}")

# Also check from opt_summary CSV (used by executive dashboard and transfer optimization page)
opt_summary = get_opt_summary(data)
print(f"\n=== From opt_summary CSV ===")
print(f"Net economic benefit: {opt_summary.get('Net economic benefit', 'N/A')}")
print(f"Total transfer cost: {opt_summary.get('Total transfer cost', 'N/A')}")
print(f"Number of recommended transfers: {opt_summary.get('Number of recommended transfers', 'N/A')}")
print(f"Total units recommended: {opt_summary.get('Total units recommended', 'N/A')}")
print(f"Unmet demand before transfers: {opt_summary.get('Unmet demand before transfers', 'N/A')}")
print(f"Unmet demand after transfers: {opt_summary.get('Unmet demand after transfers', 'N/A')}")

print(f"\n=== Static unmet (executive dashboard) ===")
print(f"Static unmet demand: {risk['total_unmet']:.0f}")

print(f"\n=== Consistency check ===")
checks = [
    ("Forecast demand ~6,385", abs(risk['total_forecast'] - 6385) < 5),
    ("Total inventory ~10,936", abs(risk['total_available'] - 10936) < 5),
    ("Transfer recs = 28", opt['num_recommendations'] == 28),
    ("Transfer units ~1,108", opt['total_units_recommended'] == 1108),
    ("Transfer cost ~2,021.50", abs(opt['total_transfer_cost'] - 2021.50) < 1),
    ("Net benefit ~44,817.17", abs(opt['net_economic_benefit'] - 44817.17) < 5),
    ("Dynamic unmet before ~1,119.7", abs(opt['baseline_unmet'] - 1119.7) < 2),
    ("Dynamic unmet after ~12.4", abs(opt['post_transfer_unmet'] - 12.4) < 1),
]
all_pass = True
for name, ok in checks:
    status = "OK" if ok else "MISMATCH"
    print(f"  {status}: {name}")
    if not ok:
        all_pass = False
print(f"\nAll consistency checks: {'PASS' if all_pass else 'FAIL'}")
