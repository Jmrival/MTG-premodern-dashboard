import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.db import get_connection
from dashboard.components.filters import sidebar_filters
from dashboard.components.charts import meta_share_pie, success_scatter
from analysis.meta_evolution import get_meta_share, get_tier_list
from analysis.success_metrics import get_archetype_success

conn = get_connection()

st.header("Meta Overview")
filters = sidebar_filters(conn)


@st.cache_data(ttl=3600)
def load_tier_list(start_date, end_date, source, min_size):
    return get_tier_list(get_connection(), min_date=start_date, max_date=end_date,
                         source=source, min_size=min_size)


@st.cache_data(ttl=3600)
def load_meta_share(start_date, end_date, source, min_size):
    return get_meta_share(get_connection(), min_date=start_date, max_date=end_date,
                          source=source, min_size=min_size)


@st.cache_data(ttl=3600)
def load_archetype_success(start_date, end_date, source, min_size):
    return get_archetype_success(get_connection(),
                                 min_date=start_date, max_date=end_date,
                                 source=source, min_tournament_size=min_size)


@st.cache_data(ttl=3600)
def load_archetype_prices(start_date, end_date, source, min_size, country="all"):
    """Average total deck price (main + side) per archetype, using cheapest card prices."""
    extra = "AND d.date >= ? AND d.date <= ?"
    params = [start_date, end_date]
    if source and source != "all":
        extra += " AND d.tournament_id IN (SELECT id FROM tournaments WHERE source = ?)"
        params.append(source)
    if country and country != "all":
        extra += " AND d.tournament_id IN (SELECT id FROM tournaments WHERE country = ?)"
        params.append(country)
    if min_size and min_size > 1:
        extra += " AND d.total_players >= ?"
        params.append(min_size)
    return pd.read_sql_query(
        f"""SELECT d.archetype,
                  ROUND(AVG(deck_total), 0) AS avg_price_usd
            FROM (
              SELECT d.id, d.archetype,
                     SUM(dc.quantity * COALESCE(c.price_usd, 0)) AS deck_total
              FROM decks d
              JOIN deck_cards dc ON dc.deck_id = d.id
              JOIN cards c ON c.name = dc.card_name
              WHERE d.cards_scraped = 1 {extra}
              GROUP BY d.id, d.archetype
              HAVING SUM(COALESCE(c.price_usd, 0)) > 0
            ) d
            GROUP BY d.archetype""",
        get_connection(), params=params,
    )


# Tier List with win rate + prices
st.subheader("Tier List (período filtrado)")
tiers = load_tier_list(filters["start_date"], filters["end_date"],
                       filters["source"], filters["min_size"])
success_period = load_archetype_success(filters["start_date"], filters["end_date"],
                                        filters["source"], filters["min_size"])
prices_df = load_archetype_prices(filters["start_date"], filters["end_date"],
                                  filters["source"], filters["min_size"],
                                  filters.get("country", "all"))
if not tiers.empty:
    if not success_period.empty:
        tiers = tiers.merge(
            success_period[["archetype", "top8_rate", "win_rate"]],
            on="archetype", how="left",
        )
    if not prices_df.empty:
        tiers = tiers.merge(prices_df, on="archetype", how="left")
    for tier in ["Tier 1", "Tier 2", "Tier 3"]:
        tier_data = tiers[tiers["tier"] == tier]
        if not tier_data.empty:
            st.markdown(f"**{tier}**")
            cols = ["archetype", "avg_share", "total_decks"]
            rename = {"archetype": "Arquetipo", "avg_share": "% Meta", "total_decks": "Mazos"}
            if "top8_rate" in tier_data.columns:
                cols += ["top8_rate", "win_rate"]
                rename.update({"top8_rate": "Top 8 %", "win_rate": "Victorias %"})
            if "avg_price_usd" in tier_data.columns:
                cols += ["avg_price_usd"]
                rename["avg_price_usd"] = "Precio Prom. (USD)"
            st.dataframe(
                tier_data[cols].rename(columns=rename),
                column_config={"Precio Prom. (USD)": st.column_config.NumberColumn(
                    "Precio Prom. (USD)", format="$%.0f"
                )},
                use_container_width=True, hide_index=True,
            )

# Meta pie chart + Success scatter
col1, col2 = st.columns(2)
with col1:
    meta_df = load_meta_share(filters["start_date"], filters["end_date"],
                               filters["source"], filters["min_size"])
    if not meta_df.empty:
        st.plotly_chart(meta_share_pie(meta_df), use_container_width=True)

with col2:
    success = load_archetype_success(filters["start_date"], filters["end_date"],
                                     filters["source"], filters["min_size"])
    if not success.empty:
        st.plotly_chart(success_scatter(success), use_container_width=True)

# Meta by source (paper vs online)
st.subheader("Meta por Fuente — Paper vs Online")
try:
    @st.cache_data(ttl=3600)
    def load_meta_by_source(start_date, end_date, min_size, country="all"):
        extra = ""
        params = [start_date, end_date, min_size]
        if country and country != "all":
            extra = " AND t.country = ?"
            params.append(country)
        return pd.read_sql_query(
            f"""SELECT d.archetype, t.source,
                      COUNT(*) as decks,
                      ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY t.source), 1) as share_pct
               FROM decks d JOIN tournaments t ON d.tournament_id = t.id
               WHERE d.date >= ? AND d.date <= ? AND d.total_players >= ?
                 AND t.source IN ('paper', 'webcam', 'mol'){extra}
               GROUP BY d.archetype, t.source""",
            get_connection(), params=params,
        )

    source_df = load_meta_by_source(
        filters["start_date"], filters["end_date"],
        filters["min_size"], filters.get("country", "all"),
    )
    if not source_df.empty:
        top_arch = source_df.groupby("archetype")["decks"].sum().nlargest(10).index
        source_top = source_df[source_df["archetype"].isin(top_arch)]
        fig_src = px.bar(
            source_top, x="archetype", y="share_pct", color="source",
            barmode="group",
            title="% Meta por Fuente — Top 10 Arquetipos",
            labels={"archetype": "Arquetipo", "share_pct": "% Meta", "source": "Fuente"},
            color_discrete_map={"paper": "#2ecc71", "webcam": "#3498db", "mol": "#e67e22"},
        )
        fig_src.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig_src, use_container_width=True)
except Exception as e:
    st.info(f"Comparación por fuente no disponible: {e}")

# Top 10 table
st.subheader("Top 10 Arquetipos - Popularidad vs Éxito")
if not success.empty:
    top10 = success.head(10).copy()
    if not prices_df.empty:
        top10 = top10.merge(prices_df, on="archetype", how="left")
    base_cols = ["archetype", "total_entries", "avg_perf_score", "top8_rate",
                 "win_rate", "consistency"]
    base_rename = {
        "archetype": "Arquetipo",
        "total_entries": "Entradas",
        "avg_perf_score": "Score Rendimiento",
        "top8_rate": "Tasa Top 8",
        "win_rate": "Tasa Victorias",
        "consistency": "Consistencia (σ)",
    }
    col_cfg = {}
    if "avg_price_usd" in top10.columns:
        base_cols.append("avg_price_usd")
        base_rename["avg_price_usd"] = "Precio Prom. (USD)"
        col_cfg["Precio Prom. (USD)"] = st.column_config.NumberColumn(
            "Precio Prom. (USD)", format="$%.0f"
        )
    st.dataframe(
        top10[base_cols].rename(columns=base_rename),
        column_config=col_cfg,
        use_container_width=True, hide_index=True,
    )

# Scatter: Top 8 % vs Precio promedio
st.subheader("Éxito vs Precio del Arquetipo")
if not success.empty and not prices_df.empty:
    scatter_df = success.merge(prices_df, on="archetype", how="inner")
    scatter_df["top8_pct"] = (scatter_df["top8_rate"] * 100).round(1)
    scatter_df["win_pct"] = (scatter_df["win_rate"] * 100).round(1)

    sc1, sc2 = st.columns(2)
    with sc1:
        fig1 = px.scatter(
            scatter_df, x="avg_price_usd", y="top8_pct",
            color="archetype", size="total_entries",
            hover_name="archetype",
            title="Top 8 % vs Precio promedio del mazo",
            labels={"avg_price_usd": "Precio promedio (USD)", "top8_pct": "Top 8 %",
                    "total_entries": "Entradas", "archetype": "Arquetipo"},
            hover_data={"archetype": False, "avg_price_usd": ":$.0f",
                        "top8_pct": ":.1f", "total_entries": True},
        )
        fig1.update_layout(xaxis_tickprefix="$", showlegend=False)
        st.plotly_chart(fig1, use_container_width=True)

    with sc2:
        fig2 = px.scatter(
            scatter_df, x="avg_price_usd", y="win_pct",
            color="archetype", size="total_entries",
            hover_name="archetype",
            title="% Victorias vs Precio promedio del mazo",
            labels={"avg_price_usd": "Precio promedio (USD)", "win_pct": "Victorias %",
                    "total_entries": "Entradas", "archetype": "Arquetipo"},
            hover_data={"archetype": False, "avg_price_usd": ":$.0f",
                        "win_pct": ":.1f", "total_entries": True},
        )
        fig2.update_layout(xaxis_tickprefix="$", showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

# Meta por País
st.subheader("Meta por País")
try:
    @st.cache_data(ttl=3600)
    def load_meta_by_country(start_date, end_date, min_size):
        return pd.read_sql_query(
            """SELECT d.archetype, t.country,
                      COUNT(*) as decks,
                      ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY t.country), 1) as share_pct
               FROM decks d JOIN tournaments t ON d.tournament_id = t.id
               WHERE d.date >= ? AND d.date <= ? AND d.total_players >= ?
                 AND t.country IS NOT NULL AND t.country != 'Unknown'
               GROUP BY d.archetype, t.country""",
            get_connection(), params=[start_date, end_date, min_size],
        )

    country_df = load_meta_by_country(filters["start_date"], filters["end_date"], filters["min_size"])
    if not country_df.empty:
        top_arch = country_df.groupby("archetype")["decks"].sum().nlargest(10).index
        top_countries = country_df.groupby("country")["decks"].sum().nlargest(8).index
        country_top = country_df[
            country_df["archetype"].isin(top_arch) & country_df["country"].isin(top_countries)
        ]
        fig_country = px.bar(
            country_top, x="archetype", y="share_pct", color="country",
            barmode="group",
            title="% Meta por País — Top 10 Arquetipos",
            labels={"archetype": "Arquetipo", "share_pct": "% Meta", "country": "País"},
        )
        fig_country.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig_country, use_container_width=True)
        st.caption("Solo torneos con país identificado. Top 8 países por volumen de torneos.")
except Exception as e:
    st.info(f"Comparación por país no disponible: {e}")
