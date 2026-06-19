import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.db import get_connection
from dashboard.components.filters import sidebar_filters
from dashboard.components.charts import trend_bar

conn = get_connection()

st.header("Cartas")
filters = sidebar_filters(conn)

has_cards = conn.execute("SELECT COUNT(*) FROM deck_cards").fetchone()[0]
if has_cards == 0:
    st.warning("No hay datos de cartas. Ejecutá el notebook 02_scrape_cards.ipynb primero.")
    st.stop()

BASIC_LANDS = ["Forest", "Island", "Mountain", "Plains", "Swamp"]


@st.cache_data(ttl=3600)
def load_type_options():
    types = pd.read_sql_query(
        "SELECT DISTINCT card_type FROM cards", get_connection()
    )["card_type"]
    return sorted(types.fillna("Sin tipo").unique().tolist())


@st.cache_data(ttl=3600)
def load_card_name_options():
    return pd.read_sql_query(
        "SELECT DISTINCT name FROM cards ORDER BY name", get_connection()
    )["name"].tolist()


# Card / type filters local to this page
st.subheader("Filtrar por tipo o carta")
fcol1, fcol2, fcol3 = st.columns([2, 2, 1])
type_options = load_type_options()
with fcol1:
    selected_types = st.multiselect("Tipos de carta", type_options, default=type_options)
with fcol2:
    selected_cards = st.multiselect(
        "Cartas específicas (vacío = todas)", load_card_name_options(), default=[]
    )
with fcol3:
    st.markdown("&nbsp;")
    exclude_basics = st.toggle("Excluir tierras básicas", value=False)


@st.cache_data(ttl=3600)
def load_top_cards(start_date, end_date, source, min_size, types, specific_cards, exclude_basics):
    extra = ""
    params = [start_date, end_date]
    if source and source != "all":
        extra += " AND t.source = ?"
        params.append(source)
    if min_size and min_size > 1:
        extra += " AND d.total_players >= ?"
        params.append(min_size)

    if types:
        actual_types = [t for t in types if t != "Sin tipo"]
        include_null = "Sin tipo" in types
        type_conditions = []
        if actual_types:
            placeholders = ",".join(["?"] * len(actual_types))
            type_conditions.append(f"c.card_type IN ({placeholders})")
            params.extend(actual_types)
        if include_null:
            type_conditions.append("c.card_type IS NULL")
        if type_conditions:
            extra += " AND (" + " OR ".join(type_conditions) + ")"

    if specific_cards:
        placeholders = ",".join(["?"] * len(specific_cards))
        extra += f" AND dc.card_name IN ({placeholders})"
        params.extend(specific_cards)

    if exclude_basics:
        placeholders = ",".join(["?"] * len(BASIC_LANDS))
        extra += f" AND dc.card_name NOT IN ({placeholders})"
        params.extend(BASIC_LANDS)

    return pd.read_sql_query(
        f"""SELECT dc.card_name, c.card_type,
                  COUNT(DISTINCT dc.deck_id) as decks,
                  SUM(dc.quantity) as total_copies,
                  ROUND(AVG(dc.quantity), 2) as avg_per_deck,
                  c.price_usd
           FROM deck_cards dc
           JOIN decks d ON dc.deck_id = d.id
           JOIN tournaments t ON d.tournament_id = t.id
           JOIN cards c ON c.name = dc.card_name
           WHERE dc.is_sideboard = 0 AND d.date >= ? AND d.date <= ?{extra}
           GROUP BY dc.card_name ORDER BY decks DESC LIMIT 100""",
        get_connection(), params=params,
    )


@st.cache_data(ttl=3600)
def load_card_search(query, source, min_size):
    extra = ""
    params = [f"%{query}%"]
    if source and source != "all":
        extra += " AND t.source = ?"
        params.append(source)
    if min_size and min_size > 1:
        extra += " AND d.total_players >= ?"
        params.append(min_size)
    return pd.read_sql_query(
        f"""SELECT dc.card_name, c.card_type, d.archetype,
                  COUNT(DISTINCT dc.deck_id) as decks,
                  ROUND(AVG(dc.quantity), 1) as avg_qty, dc.is_sideboard
           FROM deck_cards dc
           JOIN decks d ON dc.deck_id = d.id
           JOIN tournaments t ON d.tournament_id = t.id
           JOIN cards c ON c.name = dc.card_name
           WHERE dc.card_name LIKE ?{extra}
           GROUP BY dc.card_name, d.archetype, dc.is_sideboard
           ORDER BY decks DESC""",
        get_connection(), params=params,
    )


@st.cache_data(ttl=3600)
def load_card_timeline(card_name):
    return pd.read_sql_query(
        """SELECT strftime('%Y-%m', d.date) as month,
                  COUNT(DISTINCT dc.deck_id) as decks
           FROM deck_cards dc JOIN decks d ON dc.deck_id = d.id
           WHERE dc.card_name = ?
           GROUP BY month ORDER BY month""",
        get_connection(), params=[card_name],
    )


# Top cards
st.subheader("Cartas más jugadas (Mainboard)")
top_cards = load_top_cards(filters["start_date"], filters["end_date"],
                            filters["source"], filters["min_size"],
                            tuple(sorted(selected_types)), tuple(sorted(selected_cards)),
                            exclude_basics)
if top_cards.empty:
    st.info("No hay cartas que coincidan con los filtros seleccionados.")
st.dataframe(
    top_cards.rename(columns={
        "card_name": "Carta", "card_type": "Tipo", "decks": "Mazos",
        "total_copies": "Copias Totales", "avg_per_deck": "Promedio/Mazo",
        "price_usd": "Precio (USD)",
    }),
    column_config={
        "Precio (USD)": st.column_config.NumberColumn("Precio (USD)", format="$%.2f"),
    },
    use_container_width=True, hide_index=True,
)

# Card type distribution pie
if not top_cards.empty and "card_type" in top_cards.columns:
    type_counts = top_cards.groupby("card_type")["decks"].sum().reset_index()
    type_counts.columns = ["Tipo", "Mazos"]
    fig_type = px.pie(type_counts, values="Mazos", names="Tipo",
                      title="Distribución por Tipo de Carta (cartas filtradas)")
    st.plotly_chart(fig_type, use_container_width=True)

# Card search
st.subheader("Buscar Carta")
card_search = st.text_input("Nombre de carta")
if card_search:
    results = load_card_search(card_search, filters["source"], filters["min_size"])
    if not results.empty:
        st.dataframe(results.rename(columns={
            "card_name": "Carta", "card_type": "Tipo", "archetype": "Arquetipo",
            "decks": "Mazos", "avg_qty": "Promedio", "is_sideboard": "Sideboard",
        }), use_container_width=True, hide_index=True)

        card_name = results["card_name"].iloc[0]
        time_data = load_card_timeline(card_name)
        if not time_data.empty:
            fig = px.line(time_data, x="month", y="decks",
                          title=f"Uso de {card_name} en el tiempo",
                          labels={"decks": "Mazos", "month": "Mes"})
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No se encontraron resultados.")

# Breakout cards
st.subheader("Cartas Destacadas")
try:
    from analysis.card_trends import get_breakout_cards

    @st.cache_data(ttl=3600)
    def load_breakout_cards():
        return get_breakout_cards(get_connection())

    breakouts = load_breakout_cards()
    if breakouts is not None and not breakouts.empty:
        display_cols = [c for c in ["card_name", "adoption_pct", "z_score"] if c in breakouts.columns]
        st.dataframe(breakouts[display_cols].rename(columns={
            "card_name": "Carta", "adoption_pct": "Adopción Actual %", "z_score": "Z-Score",
        }), use_container_width=True, hide_index=True)
    else:
        st.info("No se detectaron cartas con z-score > 3σ en el período actual.")
except ImportError:
    st.info("Módulo de tendencias no disponible (scipy requerido).")
except Exception as e:
    st.info(f"Breakout cards no disponible: {e}")

# Card trends
st.subheader("Tendencias de Cartas")
try:
    from analysis.card_trends import detect_trends

    @st.cache_data(ttl=3600)
    def load_trends():
        return detect_trends(get_connection())

    trends = load_trends()
    if not trends.empty:
        significant = trends[trends["significant"]]
        if not significant.empty:
            st.plotly_chart(trend_bar(significant), use_container_width=True)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**En Alza**")
                rising = significant[significant["direction"] == "rising"].head(10)
                st.dataframe(rising[["card_name", "slope", "current_adoption"]].rename(
                    columns={"card_name": "Carta", "slope": "Tendencia",
                             "current_adoption": "Adopción Actual %"}
                ), hide_index=True)
            with col2:
                st.markdown("**En Baja**")
                falling = significant[significant["direction"] == "falling"].tail(10)
                st.dataframe(falling[["card_name", "slope", "current_adoption"]].rename(
                    columns={"card_name": "Carta", "slope": "Tendencia",
                             "current_adoption": "Adopción Actual %"}
                ), hide_index=True)
        else:
            st.info("No se detectaron tendencias significativas con los datos actuales.")
except ImportError:
    st.info("Módulo de tendencias no disponible (scipy requerido).")
except Exception as e:
    st.info(f"Análisis de tendencias no disponible: {e}")
