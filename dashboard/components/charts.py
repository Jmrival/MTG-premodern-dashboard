import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def meta_share_area(df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Stacked area chart of meta share over time."""
    top = df.groupby("archetype")["deck_count"].sum().nlargest(top_n).index
    filtered = df[df["archetype"].isin(top)]

    fig = px.area(
        filtered, x="month", y="meta_share_pct", color="archetype",
        title=f"Meta Share - Top {top_n} Arquetipos",
        labels={"meta_share_pct": "% del Meta", "month": "Mes"},
    )
    fig.update_layout(hovermode="x unified", legend_title="Arquetipo")
    return fig


def meta_share_pie(df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Pie chart of current meta share."""
    latest_month = df["month"].max()
    current = df[df["month"] == latest_month].nlargest(top_n, "meta_share_pct")
    others = 100 - current["meta_share_pct"].sum()

    if others > 0:
        other_row = pd.DataFrame([{
            "archetype": "Otros", "meta_share_pct": others
        }])
        current = pd.concat([current, other_row], ignore_index=True)

    fig = px.pie(
        current, values="meta_share_pct", names="archetype",
        title=f"Meta Share - {latest_month}",
    )
    return fig


def success_scatter(df: pd.DataFrame) -> go.Figure:
    """Scatter: popularity vs success rate."""
    fig = px.scatter(
        df, x="total_entries", y="top8_rate", size="total_entries",
        color="archetype", hover_name="archetype",
        title="Popularidad vs Éxito",
        labels={"total_entries": "Entradas Totales", "top8_rate": "Tasa Top 8"},
    )
    fig.update_layout(showlegend=False)
    return fig


def trend_bar(df: pd.DataFrame, n: int = 10) -> go.Figure:
    """Bar chart of rising/falling cards."""
    rising = df[df["slope"] > 0].head(n)
    falling = df[df["slope"] < 0].tail(n)
    combined = pd.concat([rising, falling])

    fig = px.bar(
        combined, x="card_name", y="slope", color="direction",
        title="Cartas en Alza / Baja",
        labels={"slope": "Tendencia", "card_name": "Carta"},
        color_discrete_map={"rising": "#2ecc71", "falling": "#e74c3c"},
    )
    fig.update_layout(xaxis_tickangle=-45)
    return fig


def heatmap_meta(pivot_df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Heatmap of archetype x month."""
    top = pivot_df.sum().nlargest(top_n).index
    data = pivot_df[top].tail(24)

    fig = go.Figure(data=go.Heatmap(
        z=data.values.T,
        x=data.index,
        y=top,
        colorscale="YlOrRd",
        colorbar_title="% Meta",
    ))
    fig.update_layout(
        title="Meta Share por Mes (últimos 24 meses)",
        xaxis_title="Mes",
        yaxis_title="Arquetipo",
    )
    return fig


def evolution_line(df: pd.DataFrame, archetype: str = "") -> go.Figure:
    """Line chart of top8_rate over time for an archetype."""
    fig = px.line(
        df, x="month", y="top8_rate",
        title=f"Evolución Win Rate — {archetype}",
        labels={"top8_rate": "Tasa Top 8", "month": "Mes"},
        markers=True,
    )
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(tickformat=".1%")
    return fig


def player_scatter(df: pd.DataFrame) -> go.Figure:
    """Scatter: total entries vs top8%, colored by distinct archetypes played."""
    fig = px.scatter(
        df,
        x="entradas",
        y="top8_pct",
        color="arquetipos",
        hover_name="player_name",
        size="entradas",
        title="Especialistas vs Experimentadores",
        labels={
            "entradas": "Entradas Totales",
            "top8_pct": "Top 8 %",
            "arquetipos": "Arquetipos Distintos",
        },
        color_continuous_scale="Viridis",
    )
    fig.update_layout(coloraxis_colorbar_title="Arquetipos")
    return fig


def cooccurrence_network(pairs_df: pd.DataFrame) -> go.Figure:
    """Network graph of card co-occurrence from PMI pairs."""
    import math

    # Build adjacency: collect unique nodes and edges
    edges = pairs_df[["card_a", "card_b", "pmi"]].values.tolist()
    nodes = list({c for row in edges for c in (row[0], row[1])})
    n = len(nodes)
    node_idx = {name: i for i, name in enumerate(nodes)}

    # Circular layout
    angle = [2 * math.pi * i / n for i in range(n)]
    xs = [math.cos(a) for a in angle]
    ys = [math.sin(a) for a in angle]

    # Edge traces
    edge_x, edge_y = [], []
    for ca, cb, pmi in edges:
        i, j = node_idx[ca], node_idx[cb]
        edge_x += [xs[i], xs[j], None]
        edge_y += [ys[i], ys[j], None]

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=0.8, color="#aaa"),
        hoverinfo="none",
    )
    node_trace = go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        text=nodes,
        textposition="top center",
        marker=dict(size=10, color="#3498db", line_width=1),
        hovertext=nodes,
        hoverinfo="text",
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        title="Red de Co-ocurrencia de Cartas (PMI)",
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=600,
    )
    return fig


def forecast_line(hist_df: pd.DataFrame, forecast_df: pd.DataFrame) -> go.Figure:
    """Historical line (solid) + forecast line (dashed) per archetype.

    forecast_df must have columns: archetype, period (int 1-N), forecast_share.
    hist_df must have columns: archetype, month (YYYY-MM str), meta_share_pct.
    """
    fig = go.Figure()
    archetypes = hist_df["archetype"].unique()
    palette = px.colors.qualitative.Plotly

    # Compute future month labels from last historical month
    last_month_str = hist_df["month"].max()
    try:
        last_month_dt = pd.to_datetime(last_month_str + "-01")
        max_periods = int(forecast_df["period"].max()) if not forecast_df.empty else 3
        future_months = [
            (last_month_dt + pd.DateOffset(months=p)).strftime("%Y-%m")
            for p in range(1, max_periods + 1)
        ]
    except Exception:
        future_months = [str(p) for p in range(1, 4)]

    for i, arch in enumerate(archetypes):
        color = palette[i % len(palette)]
        h = hist_df[hist_df["archetype"] == arch].sort_values("month")
        f = forecast_df[forecast_df["archetype"] == arch].sort_values("period")

        fig.add_trace(go.Scatter(
            x=h["month"], y=h["meta_share_pct"],
            mode="lines", name=arch,
            line=dict(color=color, width=2),
            legendgroup=arch,
        ))
        if not f.empty:
            f_months = [future_months[int(p) - 1] for p in f["period"] if int(p) - 1 < len(future_months)]
            bridge_x = [h["month"].iloc[-1]] + f_months
            bridge_y = [h["meta_share_pct"].iloc[-1]] + f["forecast_share"].tolist()
            fig.add_trace(go.Scatter(
                x=bridge_x, y=bridge_y,
                mode="lines", name=f"{arch} (forecast)",
                line=dict(color=color, width=2, dash="dot"),
                legendgroup=arch, showlegend=False,
            ))

    fig.update_layout(
        title="Histórico + Forecast del Meta",
        xaxis_title="Período",
        yaxis_title="% Meta",
        hovermode="x unified",
        legend_title="Arquetipo",
    )
    return fig


def mana_curve_bar(curve_df: pd.DataFrame, avg_lands: float,
                   avg_cmc: float | None, archetype: str = "") -> go.Figure:
    """Mana curve: one bar per CMC bucket (0..6+) plus a separate bar for lands,
    with a vertical line marking the average non-land CMC."""
    labels = [str(b) if b < 6 else "6+" for b in curve_df["bucket"]]
    x_positions = list(range(len(labels)))
    lands_x = len(labels)
    labels.append("Tierras")
    x_positions.append(lands_x)

    values = curve_df["avg_copies"].tolist() + [avg_lands]
    colors = ["#3498db"] * len(curve_df) + ["#95a5a6"]

    fig = go.Figure(go.Bar(
        x=x_positions, y=values, marker_color=colors,
        text=[f"{v:.1f}" for v in values], textposition="outside",
    ))
    fig.update_xaxes(tickmode="array", tickvals=x_positions, ticktext=labels,
                     title="Coste de maná (CMC)")
    fig.update_yaxes(title="Copias promedio por mazo")

    if avg_cmc is not None:
        fig.add_vline(
            x=avg_cmc, line_dash="dash", line_color="#e74c3c",
            annotation_text=f"CMC promedio (sin tierras): {avg_cmc:.2f}",
            annotation_position="top",
        )

    fig.update_layout(title=f"Mana Curve — {archetype}", showlegend=False)
    return fig


def umap_scatter(df: pd.DataFrame) -> go.Figure:
    """UMAP scatter plot colored by archetype or cluster."""
    fig = px.scatter(
        df, x="umap_x", y="umap_y", color="archetype",
        hover_data=["deck_id", "cluster"],
        title="Clustering de Mazos (UMAP + HDBSCAN)",
        labels={"umap_x": "UMAP 1", "umap_y": "UMAP 2"},
    )
    fig.update_traces(marker_size=3, marker_opacity=0.6)
    fig.update_layout(legend_title="Arquetipo")
    return fig
