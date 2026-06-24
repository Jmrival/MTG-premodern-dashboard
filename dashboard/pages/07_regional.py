import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.db import get_connection
from dashboard.components.filters import sidebar_filters

conn = get_connection()

st.header("Análisis Regional")
filters = sidebar_filters(conn)

f_start = filters["start_date"]
f_end = filters["end_date"]
f_min = filters["min_size"]
f_source = filters.get("source", "all")
f_archetypes = tuple(filters.get("archetypes", []))


@st.cache_data(ttl=3600)
def load_country_volume(start_date, end_date, min_size, source="all", archetypes=()):
    extra = ""
    params = [start_date, end_date, min_size]
    if source and source != "all":
        extra += " AND t.source = ?"
        params.append(source)
    if archetypes:
        placeholders = ",".join(["?"] * len(archetypes))
        extra += f" AND d.archetype IN ({placeholders})"
        params.extend(archetypes)
    return pd.read_sql_query(
        f"""SELECT t.country,
                  COUNT(DISTINCT t.id)          AS torneos,
                  COUNT(DISTINCT d.id)           AS mazos,
                  COUNT(DISTINCT d.player_name)  AS jugadores,
                  MIN(t.date)                    AS primer_torneo,
                  MAX(t.date)                    AS ultimo_torneo,
                  ROUND(AVG(t.player_count), 0)  AS promedio_jugadores
           FROM tournaments t
           JOIN decks d ON d.tournament_id = t.id
           WHERE t.country IS NOT NULL AND t.country != 'Unknown'
             AND t.date >= ? AND t.date <= ? AND t.player_count >= ?{extra}
           GROUP BY t.country
           ORDER BY torneos DESC""",
        get_connection(), params=params,
    )


@st.cache_data(ttl=3600)
def load_meta_by_country(start_date, end_date, min_size, countries, source="all", archetypes=()):
    if not countries:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(countries))
    extra = ""
    params = list(countries) + [start_date, end_date, min_size]
    if source and source != "all":
        extra += " AND t.source = ?"
        params.append(source)
    if archetypes:
        arch_placeholders = ",".join(["?"] * len(archetypes))
        extra += f" AND d.archetype IN ({arch_placeholders})"
        params.extend(archetypes)
    return pd.read_sql_query(
        f"""SELECT d.archetype, t.country,
                  COUNT(*) AS decks,
                  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY t.country), 1) AS share_pct
           FROM decks d JOIN tournaments t ON d.tournament_id = t.id
           WHERE t.country IN ({placeholders})
             AND t.date >= ? AND t.date <= ? AND t.player_count >= ?{extra}
           GROUP BY d.archetype, t.country""",
        get_connection(), params=params,
    )


@st.cache_data(ttl=3600)
def load_archetype_evolution_by_country(archetype, start_date, end_date, min_size, countries,
                                        source="all"):
    if not countries:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(countries))
    extra = ""
    params = [archetype] + list(countries) + [start_date, end_date, min_size]
    if source and source != "all":
        extra += " AND t.source = ?"
        params.append(source)
    return pd.read_sql_query(
        f"""SELECT strftime('%Y-%m', d.date) AS month,
                  t.country,
                  COUNT(*) AS decks,
                  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY strftime('%Y-%m', d.date), t.country), 1) AS share_pct
           FROM decks d JOIN tournaments t ON d.tournament_id = t.id
           WHERE d.archetype = ? AND t.country IN ({placeholders})
             AND t.date >= ? AND t.date <= ? AND t.player_count >= ?{extra}
           GROUP BY month, t.country
           ORDER BY month""",
        get_connection(),
        params=params,
    )


@st.cache_data(ttl=3600)
def load_recent_by_country(start_date, end_date, min_size, country, source="all"):
    extra = ""
    params = [country, start_date, end_date, min_size]
    if source and source != "all":
        extra += " AND t.source = ?"
        params.append(source)
    return pd.read_sql_query(
        f"""SELECT t.name AS torneo, t.date, t.country, t.player_count AS jugadores,
                  (SELECT d2.player_name FROM decks d2
                   WHERE d2.tournament_id = t.id AND d2.position = 1
                   LIMIT 1) AS ganador,
                  (SELECT d2.archetype FROM decks d2
                   WHERE d2.tournament_id = t.id AND d2.position = 1
                   LIMIT 1) AS arquetipo_ganador
           FROM tournaments t
           WHERE t.country = ? AND t.date >= ? AND t.date <= ? AND t.player_count >= ?{extra}
           ORDER BY t.date DESC LIMIT 30""",
        get_connection(), params=params,
    )


# ── Volumen por país ──────────────────────────────────────────────────────────
st.subheader("Volumen por País")
vol_df = load_country_volume(f_start, f_end, f_min, f_source, f_archetypes)
if vol_df.empty:
    st.info("No hay datos geográficos para el período seleccionado. "
            "Corré `python db/detect_location.py db/premodern.db` primero.")
    st.stop()

col_vol, col_bar = st.columns([2, 3])
with col_vol:
    st.dataframe(
        vol_df.rename(columns={
            "country": "País", "torneos": "Torneos", "mazos": "Mazos",
            "jugadores": "Jugadores únicos", "primer_torneo": "Desde",
            "ultimo_torneo": "Hasta", "promedio_jugadores": "Prom. jugadores",
        }),
        width="stretch", hide_index=True,
    )
with col_bar:
    fig_vol = px.bar(
        vol_df.head(12), x="torneos", y="country", orientation="h",
        title="Torneos por País", color="torneos",
        color_continuous_scale="Blues",
        labels={"torneos": "Torneos", "country": "País"},
    )
    fig_vol.update_layout(showlegend=False, coloraxis_showscale=False, yaxis={"autorange": "reversed"})
    st.plotly_chart(fig_vol, width="stretch")

# ── Comparación de meta por país ──────────────────────────────────────────────
st.subheader("Comparación de Meta por País")
available_countries = vol_df["country"].tolist()
default_countries = available_countries[:4]

selected_countries = st.multiselect(
    "Seleccioná países a comparar",
    available_countries,
    default=default_countries,
)

if selected_countries:
    meta_df = load_meta_by_country(f_start, f_end, f_min, tuple(selected_countries), f_source, f_archetypes)
    if not meta_df.empty:
        top_arch = meta_df.groupby("archetype")["decks"].sum().nlargest(12).index
        meta_top = meta_df[meta_df["archetype"].isin(top_arch)]

        view = st.radio("Vista", ["Grouped", "Stacked"], horizontal=True)
        fig_meta = px.bar(
            meta_top, x="archetype", y="share_pct", color="country",
            barmode="group" if view == "Grouped" else "stack",
            title="% Meta Share por País — Top 12 Arquetipos",
            labels={"archetype": "Arquetipo", "share_pct": "% Meta", "country": "País"},
        )
        fig_meta.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig_meta, width="stretch")

# ── Evolución de un arquetipo por país ────────────────────────────────────────
st.subheader("Evolución de Arquetipo por País")
archetypes = pd.read_sql_query(
    "SELECT DISTINCT archetype FROM decks ORDER BY archetype", conn
)["archetype"].tolist()

evo_col1, evo_col2 = st.columns([2, 3])
with evo_col1:
    selected_arch = st.selectbox("Arquetipo", archetypes)
    evo_countries = st.multiselect(
        "Países", available_countries, default=available_countries[:5],
        key="evo_countries",
    )

if selected_arch and evo_countries:
    evo_df = load_archetype_evolution_by_country(
        selected_arch, f_start, f_end, f_min, tuple(evo_countries), f_source
    )
    if not evo_df.empty:
        fig_evo = px.line(
            evo_df, x="month", y="share_pct", color="country",
            title=f"Meta Share de {selected_arch} por País",
            labels={"month": "Mes", "share_pct": "% Meta", "country": "País"},
            markers=True,
        )
        st.plotly_chart(fig_evo, width="stretch")
    else:
        st.info("Sin datos suficientes para este arquetipo en los países seleccionados.")

# ── Últimos torneos por país ──────────────────────────────────────────────────
st.subheader("Últimos Torneos por País")
detail_country = st.selectbox("País", available_countries, key="detail_country")
if detail_country:
    recent_df = load_recent_by_country(f_start, f_end, f_min, detail_country, f_source)
    if not recent_df.empty:
        st.dataframe(
            recent_df.rename(columns={
                "torneo": "Torneo", "date": "Fecha", "country": "País",
                "jugadores": "Jugadores", "ganador": "Ganador",
                "arquetipo_ganador": "Arquetipo ganador",
            }),
            width="stretch", hide_index=True,
        )
    else:
        st.info("No hay torneos para este país en el período seleccionado.")
