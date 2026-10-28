"""Reusable Plotly chart builders for TradeFlow AI dashboard."""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from components.styling import RISK_COLORS, WAREHOUSE_COLORS, APPROVAL_COLORS, CATEGORY_COLORS, BLUE, TEAL, GREEN, ORANGE, RED, GRAY


# ── Default layout template ──
_LAYOUT = dict(
    margin=dict(l=40, r=20, t=60, b=45),
    font=dict(family="Segoe UI, Arial, sans-serif", size=13, color="#111827"),
    paper_bgcolor="white",
    plot_bgcolor="white",
    hoverlabel=dict(bgcolor="#1A2B45", font_size=13),
    legend=dict(
        font=dict(size=11, color="#374151"),
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
    title_y=0.95,
)
_CONFIG = dict(displayModeBar=False, responsive=True)


def _apply_layout(fig, title=""):
    fig.update_layout(**_LAYOUT)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=16, color="#111827"), x=0.01))
    fig.update_xaxes(gridcolor="#E5E7EB", zerolinecolor="#E5E7EB", tickfont=dict(size=12, color="#374151"))
    fig.update_yaxes(gridcolor="#E5E7EB", zerolinecolor="#E5E7EB", tickfont=dict(size=12, color="#374151"))
    return fig


# ══════════════════════════════════════════════════════════════
# Bar charts
# ══════════════════════════════════════════════════════════════

def inventory_by_warehouse(inv_df: pd.DataFrame) -> go.Figure:
    """Bar chart: available stock by warehouse."""
    wh_data = inv_df.groupby("Warehouse")["Available_Stock"].sum().reset_index()
    wh_data = wh_data.sort_values("Available_Stock", ascending=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=wh_data["Available_Stock"],
        y=wh_data["Warehouse"],
        orientation="h",
        marker_color=[WAREHOUSE_COLORS.get(w, BLUE) for w in wh_data["Warehouse"]],
        text=wh_data["Available_Stock"],
        textposition="outside",
        texttemplate="%{text:,.0f}",
        hovertemplate="<b>%{y}</b><br>Available: %{x:,.0f} units<extra></extra>",
    ))
    fig = _apply_layout(fig, "Inventory Distribution by Warehouse")
    fig.update_xaxes(title="Available Stock (units)")
    return fig


def risk_distribution_pie(risk_counts: dict) -> go.Figure:
    """Donut chart: risk distribution."""
    labels = list(risk_counts.keys())
    values = list(risk_counts.values())
    colors = [RISK_COLORS.get(l, GRAY) for l in labels]
    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker=dict(colors=[RISK_COLORS.get(l, "#6B7280") for l in labels]),
        textinfo="label+value",
        textposition="outside",
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>",
    ))
    fig = _apply_layout(fig, "Inventory Risk Distribution")
    return fig


def risk_distribution_bar(by_warehouse: dict) -> go.Figure:
    """Stacked bar chart: risk counts by warehouse."""
    warehouses = list(by_warehouse.keys())
    risk_types = ["Critical", "Warning", "Excess", "Healthy"]
    fig = go.Figure()
    for risk in risk_types:
        values = [by_warehouse[wh].get(risk.lower(), 0) for wh in warehouses]
        fig.add_trace(go.Bar(
            name=risk,
            x=warehouses,
            y=values,
            marker_color=RISK_COLORS.get(risk, "#6B7280"),
            hovertemplate=f"<b>{risk}</b><br>%{{x}}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig = _apply_layout(fig, "Risk Distribution by Warehouse")
    fig.update_yaxes(title="SKU-Warehouse Combos")
    return fig


# ══════════════════════════════════════════════════════════════
# Line charts
# ══════════════════════════════════════════════════════════════

def forecast_line(daily_forecast_df: pd.DataFrame, sku: str, warehouse: str,
                  period_days: int = 30) -> go.Figure:
    """Line chart: daily demand forecast for a SKU/warehouse."""
    df = daily_forecast_df[
        (daily_forecast_df["SKU"] == sku) &
        (daily_forecast_df["Warehouse"] == warehouse)
    ].sort_values("Date").head(period_days)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"],
        y=df["Predicted_Demand"],
        mode="lines+markers",
        line=dict(color=BLUE, width=2),
        marker=dict(size=4),
        hovertemplate="<b>%{x}</b><br>Demand: %{y:.1f} units<extra></extra>",
    ))
    fig = _apply_layout(fig, f"Daily Demand Forecast — {sku} at {warehouse}")
    fig.update_yaxes(title="Predicted Demand")
    return fig


def forecast_with_bounds(daily_df: pd.DataFrame, fc30_row: pd.Series, sku: str, warehouse: str) -> go.Figure:
    """Forecast line with upper/lower bounds band.

    The 30-day aggregate uncertainty (Upper_Bound/Lower_Bound around Forecast_30d)
    is distributed evenly across days. Each day's band is centered on that day's
    own prediction, so the band follows the forecast rather than being a flat line.
    """
    df = daily_df[
        (daily_df["SKU"] == sku) &
        (daily_df["Warehouse"] == warehouse)
    ].sort_values("Date")
    n_days = len(df)
    if n_days == 0:
        # Fallback: empty figure
        fig = go.Figure()
        fig = _apply_layout(fig, f"Forecast with Uncertainty — {sku} at {warehouse}")
        fig.update_yaxes(title="Predicted Demand")
        return fig

    # Daily margin derived from the 30-day aggregate bounds
    daily_upper_margin = (fc30_row["Upper_Bound"] - fc30_row["Forecast_30d"]) / n_days
    daily_lower_margin = (fc30_row["Forecast_30d"] - fc30_row["Lower_Bound"]) / n_days

    # Per-day upper/lower centered on each day's prediction
    preds = df["Predicted_Demand"].values
    upper_series = preds + daily_upper_margin
    lower_series = np.maximum(0.0, preds - daily_lower_margin)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(df["Date"]) + list(df["Date"][::-1]),
        y=list(upper_series) + list(lower_series[::-1]),
        fill="toself",
        fillcolor="rgba(37,99,235,0.12)",
        line=dict(color="rgba(0,0,0,0)"),
        name="Uncertainty Band",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df["Date"],
        y=df["Predicted_Demand"],
        mode="lines+markers",
        line=dict(color=BLUE, width=2.5),
        marker=dict(size=4),
        name="Forecast",
        hovertemplate="<b>%{x}</b><br>Demand: %{y:.1f}<extra></extra>",
    ))
    fig = _apply_layout(fig, f"Forecast with Uncertainty — {sku} at {warehouse}")
    fig.update_yaxes(title="Predicted Demand")
    return fig


def historical_vs_forecast(sales_df: pd.DataFrame, daily_fc_df: pd.DataFrame,
                           sku: str, warehouse: str) -> go.Figure:
    """Historical sales vs forecast demand."""
    hist = sales_df[
        (sales_df["SKU"] == sku) &
        (sales_df["Warehouse"] == warehouse)
    ].sort_values("Date").tail(30)
    fc = daily_fc_df[
        (daily_fc_df["SKU"] == sku) &
        (daily_fc_df["Warehouse"] == warehouse)
    ].sort_values("Date")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist["Date"], y=hist["Units_Sold"],
        mode="lines", line=dict(color=GRAY, width=2),
        name="Historical Sales (last 30d)",
        hovertemplate="<b>%{x}</b><br>Sold: %{y:.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=fc["Date"], y=fc["Predicted_Demand"],
        mode="lines", line=dict(color=BLUE, width=2.5, dash="dot"),
        name="Forecast Demand (next 30d)",
        hovertemplate="<b>%{x}</b><br>Forecast: %{y:.1f}<extra></extra>",
    ))
    fig = _apply_layout(fig, f"Historical vs Forecast — {sku} at {warehouse}")
    fig.update_yaxes(title="Units")
    return fig


def forecast_all_warehouses(daily_df: pd.DataFrame, sku: str) -> go.Figure:
    """Daily forecast for a SKU across all warehouses."""
    df = daily_df[daily_df["SKU"] == sku].sort_values("Date")
    fig = go.Figure()
    for wh in df["Warehouse"].unique():
        wh_df = df[df["Warehouse"] == wh]
        fig.add_trace(go.Scatter(
            x=wh_df["Date"], y=wh_df["Predicted_Demand"],
            mode="lines", line=dict(color=WAREHOUSE_COLORS.get(wh, BLUE), width=2),
            name=wh,
            hovertemplate=f"<b>{wh}</b><br>%{{x}}: %{{y:.1f}}<extra></extra>",
        ))
    fig = _apply_layout(fig, f"Daily Forecast by Warehouse — {sku}")
    fig.update_yaxes(title="Predicted Demand")
    return fig


# ══════════════════════════════════════════════════════════════
# Transfer / optimization charts
# ══════════════════════════════════════════════════════════════

def transfer_network(recs_df: pd.DataFrame) -> go.Figure:
    """Sankey-style transfer network between warehouses."""
    if recs_df.empty:
        fig = go.Figure()
        fig.update_layout(annotations=[dict(text="No transfers to display", showarrow=False)])
        return _apply_layout(fig, "Transfer Network")

    # Aggregate by source-destination
    agg = recs_df.groupby(["source_warehouse", "destination_warehouse"]).agg(
        total_qty=("transfer_quantity", "sum"),
        total_cost=("transfer_cost_aed", "sum"),
        count=("transfer_quantity", "count"),
    ).reset_index()

    # Build node list
    all_wh = list(set(agg["source_warehouse"].tolist() + agg["destination_warehouse"].tolist()))
    node_map = {w: i for i, w in enumerate(all_wh)}

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=25,
            thickness=28,
            line=dict(color="#E5E7EB", width=1),
            label=all_wh,
            color=[WAREHOUSE_COLORS.get(w, BLUE) for w in all_wh],
        ),
        link=dict(
            source=[node_map[s] for s in agg["source_warehouse"]],
            target=[node_map[d] for d in agg["destination_warehouse"]],
            value=agg["total_qty"],
            color="rgba(37,99,235,0.25)",
            hovertemplate="<b>%{source.label} → %{target.label}</b><br>"
                          "Units: %{value}<extra></extra>",
        ),
        textfont=dict(size=13, color="#111827"),
    ))
    fig = _apply_layout(fig, "Warehouse Transfer Network")
    return fig


def transfer_bar(recs_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of transfer quantities by route."""
    if recs_df.empty:
        fig = go.Figure()
        fig.update_layout(annotations=[dict(text="No transfers to display", showarrow=False)])
        return _apply_layout(fig, "Transfer Quantities")

    recs_df = recs_df.copy()
    recs_df["route"] = recs_df["source_warehouse"] + " → " + recs_df["destination_warehouse"]
    recs_df = recs_df.sort_values("transfer_quantity", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=recs_df["route"] + " (" + recs_df["sku"] + ")",
        x=recs_df["transfer_quantity"],
        orientation="h",
        marker_color=[WAREHOUSE_COLORS.get(s, BLUE) for s in recs_df["source_warehouse"]],
        text=recs_df["transfer_quantity"],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Qty: %{x} units<extra></extra>",
    ))
    fig = _apply_layout(fig, "Transfer Quantities by Route")
    fig.update_xaxes(title="Units")
    return fig


def before_after_comparison(before: float, after: float, title="Unmet Demand") -> go.Figure:
    """Bar chart: before vs after comparison."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["Before Transfers", "After Transfers"],
        y=[before, after],
        marker_color=[RED, GREEN],
        text=[f"{before:,.1f}", f"{after:,.1f}"],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y:,.1f} units<extra></extra>",
    ))
    fig = _apply_layout(fig, f"{title}: Before vs After Optimization")
    fig.update_yaxes(title="Units")
    return fig


def economic_impact_chart(cost: float, margin_preserved: float, net_benefit: float) -> go.Figure:
    """Waterfall-style chart for economic impact."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["Transfer Cost", "Margin Preserved", "Net Benefit"],
        y=[-cost, margin_preserved, net_benefit],
        marker_color=[RED, GREEN, BLUE],
        text=[f"-{cost:,.0f}", f"+{margin_preserved:,.0f}", f"{net_benefit:,.0f}"],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y:,.2f} AED<extra></extra>",
    ))
    fig = _apply_layout(fig, "Economic Impact (AED)")
    fig.update_yaxes(title="AED")
    return fig


# ══════════════════════════════════════════════════════════════
# Inventory ageing
# ══════════════════════════════════════════════════════════════

def ageing_chart(ageing_df: pd.DataFrame, warehouse: str = "All") -> go.Figure:
    """Stacked bar chart for inventory ageing."""
    df = ageing_df.copy()
    if warehouse != "All":
        df = df[df["Warehouse"] == warehouse]
    # Normalise Age_Bucket labels: CSV has "0-30 days" but legacy code expects "0-30"
    df["Age_Bucket"] = df["Age_Bucket"].str.replace(" days", "", regex=False)
    pivot = df.groupby("Age_Bucket")["Quantity"].sum().reset_index()
    order = ["0-30", "31-60", "61-90", "90+"]
    pivot["sort"] = pivot["Age_Bucket"].apply(lambda x: order.index(x) if x in order else 99)
    pivot = pivot.sort_values("sort")

    fig = go.Figure()
    colors = [GREEN, BLUE, ORANGE, RED]
    fig.add_trace(go.Bar(
        x=pivot["Age_Bucket"],
        y=pivot["Quantity"],
        marker_color=colors[:len(pivot)],
        text=pivot["Quantity"],
        textposition="outside",
        hovertemplate="<b>%{x} days</b><br>Quantity: %{y:,.0f}<extra></extra>",
    ))
    fig = _apply_layout(fig, f"Inventory Ageing Distribution ({warehouse})")
    fig.update_xaxes(title="Age Bucket (days)")
    fig.update_yaxes(title="Quantity (units)")
    return fig


def ageing_by_sku(ageing_df: pd.DataFrame, warehouse: str = "All") -> go.Figure:
    """Stacked bar: ageing by SKU."""
    df = ageing_df.copy()
    if warehouse != "All":
        df = df[df["Warehouse"] == warehouse]
    # Normalise Age_Bucket labels: CSV has "0-30 days" but legacy code expects "0-30"
    df["Age_Bucket"] = df["Age_Bucket"].str.replace(" days", "", regex=False)
    pivot = df.pivot_table(index="SKU", columns="Age_Bucket", values="Quantity", fill_value=0)
    for col in ["0-30", "31-60", "61-90", "90+"]:
        if col not in pivot.columns:
            pivot[col] = 0
    pivot = pivot[["0-30", "31-60", "61-90", "90+"]]

    fig = go.Figure()
    colors = {"0-30": GREEN, "31-60": BLUE, "61-90": ORANGE, "90+": RED}
    for col in pivot.columns:
        fig.add_trace(go.Bar(
            name=col, x=pivot.index, y=pivot[col],
            marker_color=colors.get(col, BLUE),
            hovertemplate=f"<b>{{{'x'}}}</b><br>{col}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig = _apply_layout(fig, "Inventory Ageing by SKU")
    fig.update_yaxes(title="Quantity")
    return fig


# ══════════════════════════════════════════════════════════════
# Inventory projection
# ══════════════════════════════════════════════════════════════

def inventory_projection(projection_df: pd.DataFrame, sku: str, warehouse: str,
                         safety_stock: float = None) -> go.Figure:
    """Daily inventory projection over 30 days."""
    df = projection_df[
        (projection_df["SKU"] == sku) &
        (projection_df["Warehouse"] == warehouse)
    ].sort_values("Date")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Ending_Stock"],
        mode="lines", line=dict(color=BLUE, width=2.5),
        name="Ending Stock",
        hovertemplate="<b>%{x}</b><br>Stock: %{y:.1f}<extra></extra>",
    ))
    if "Unmet_Demand" in df.columns:
        fig.add_trace(go.Bar(
            x=df["Date"], y=df["Unmet_Demand"],
            name="Unmet Demand",
            marker_color="rgba(220,38,38,0.3)",
            hovertemplate="<b>%{x}</b><br>Unmet: %{y:.1f}<extra></extra>",
        ))
    if safety_stock is not None:
        fig.add_hline(y=safety_stock, line_dash="dash", line_color=ORANGE,
                      annotation_text=f"Safety Stock ({safety_stock:.0f})",
                      annotation_position="bottom right")
    fig = _apply_layout(fig, f"Inventory Projection — {sku} at {warehouse}")
    fig.update_yaxes(title="Stock Level")
    return fig


# ══════════════════════════════════════════════════════════════
# Warehouse comparison
# ══════════════════════════════════════════════════════════════

def warehouse_comparison(inv_df: pd.DataFrame, forecast_30d: pd.DataFrame) -> go.Figure:
    """Grouped bar chart comparing warehouses."""
    merged = inv_df.merge(forecast_30d[["SKU", "Warehouse", "Forecast_30d"]],
                          on=["SKU", "Warehouse"])
    wh_data = merged.groupby("Warehouse").agg(
        Available=("Available_Stock", "sum"),
        Forecast=("Forecast_30d", "sum"),
        Safety=("Safety_Stock", "sum"),
    ).reset_index()

    fig = go.Figure()
    for col, color, name in [("Available", BLUE, "Available Stock"),
                             ("Forecast", ORANGE, "Forecast 30d"),
                             ("Safety", GREEN, "Safety Stock")]:
        fig.add_trace(go.Bar(
            name=name, x=wh_data["Warehouse"], y=wh_data[col],
            marker_color=color,
            hovertemplate=f"<b>{{{'x'}}}</b><br>{name}: %{{y:,.0f}}<extra></extra>",
        ))
    fig.update_layout(barmode="group")
    fig = _apply_layout(fig, "Warehouse Comparison")
    fig.update_yaxes(title="Units")
    return fig


def warehouse_radar(inv_df: pd.DataFrame, forecast_30d: pd.DataFrame) -> go.Figure:
    """Radar chart comparing warehouse risk metrics."""
    merged = inv_df.merge(forecast_30d[["SKU", "Warehouse", "Forecast_30d"]],
                          on=["SKU", "Warehouse"])
    metrics = {}
    for wh in merged["Warehouse"].unique():
        wd = merged[merged["Warehouse"] == wh]
        unmet = (wd["Forecast_30d"] - wd["Available_Stock"]).clip(lower=0).sum()
        excess = (wd["Available_Stock"] - wd["Forecast_30d"] - wd["Safety_Stock"]).clip(lower=0).sum()
        coverage = wd["Available_Stock"].sum() / wd["Forecast_30d"].sum() if wd["Forecast_30d"].sum() > 0 else 0
        metrics[wh] = {"Unmet Demand": unmet, "Excess Stock": excess, "Coverage Ratio": coverage * 100}

    categories = ["Unmet Demand", "Excess Stock", "Coverage Ratio"]
    fig = go.Figure()
    for wh, vals in metrics.items():
        fig.add_trace(go.Scatterpolar(
            r=[vals[c] for c in categories] + [vals[categories[0]]],
            theta=categories + [categories[0]],
            fill="toself",
            name=wh,
            line=dict(color=WAREHOUSE_COLORS.get(wh, BLUE)),
        ))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, max(max(v.values()) for v in metrics.values()) * 1.2])))
    fig = _apply_layout(fig, "Warehouse Risk Radar")
    return fig


# ══════════════════════════════════════════════════════════════
# Approved-plan impact
# ══════════════════════════════════════════════════════════════

def approval_impact_chart(proposed_benefit: float, approved_benefit: float,
                           rejected_benefit: float, pending_benefit: float) -> go.Figure:
    """Bar chart showing benefit breakdown by approval status."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["Approved", "Pending", "Rejected", "Total Proposed"],
        y=[approved_benefit, pending_benefit, rejected_benefit, proposed_benefit],
        marker_color=[GREEN, ORANGE, RED, BLUE],
        text=[f"{v:,.0f}" for v in [approved_benefit, pending_benefit, rejected_benefit, proposed_benefit]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Benefit: %{y:,.2f} AED<extra></extra>",
    ))
    fig = _apply_layout(fig, "Economic Benefit by Approval Status")
    fig.update_yaxes(title="Net Benefit (AED)")
    return fig
