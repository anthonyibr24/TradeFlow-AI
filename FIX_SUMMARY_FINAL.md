# TradeFlow AI — Final Bug Fixes

## Bugs Fixed

1. **TypeError: TextColumn() got an unexpected keyword argument 'align'**
   - Removed `align="right"` from all `st.column_config.TextColumn()` calls in `_render_comparison_table()` in `pages/agent_control_center.py`. Both simulators now render correctly.

2. **Forecast uncertainty band not following prediction line**
   - Root cause: `forecast_with_bounds()` in `components/charts.py` built the band as a **flat horizontal rectangle** using `avg_daily` (a constant). The daily forecast line varied day-to-day, so predictions fell outside the band.
   - Fix: Band is now **centered on each day's own prediction**. The 30-day aggregate uncertainty margin (`Upper_Bound - Forecast_30d`) is distributed evenly per day, then added/subtracted from each day's `Predicted_Demand`.
   - Verified: all 30 daily predictions for SKU-001 at Abu Dhabi now lie within their corresponding upper/lower bounds. Band std = 0.28 (no longer flat).

3. **UI visibility** — Already fixed in prior session (sidebar headings white, chart titles dark text, KPI truncation). No further changes needed.

## Files Modified

| File | Change |
|------|--------|
| `pages/agent_control_center.py` | Removed `align="right"` from `TextColumn()` config (lines 714-716) |
| `components/charts.py` | Rewrote `forecast_with_bounds()` — band now tracks daily predictions instead of flat constant |

## Tests Passed

- **Smoke tests:** 15/15 passed
- **Regression tests:** 17/17 passed
- **Uncertainty band verification:** All predictions within bounds, band varies with forecast
- **Comparison table:** No `align=` kwarg, uses `st.dataframe`, no raw HTML

## Remaining Limitations

1. **Visual browser inspection not performed** — fixes verified via code inspection and automated tests only
2. **Disruption simulator KPIs may remain unchanged** — verified in prior session this is correct behavior; explanation now clearly states why
