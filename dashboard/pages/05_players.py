import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.db import get_connection
from dashboard.components.filters import sidebar_filters
from dashboard.components.charts import player_scatter

conn = get_connection()

st.header("Jugadores")
filters = sidebar_filters(conn)


@st.cache_data(ttl=3600)
def load_leaderboard(start_date, end_date, source, min_size):
    extra = ""
    params = [start_date, end_date, min_size]
    if source and source != "all":
        extra = " AND tournament_id IN (SELECT id FROM tournaments WHERE source = ?)"
        params.insert(2, source)  # insert before min_size
    return pd.read_sql_query(
        f"""SELECT player_name,
                  COUNT(*) as entradas,
                  COUNT(DISTINCT tournament_id) as torneos,
                  SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as victorias,
                  SUM(CASE WHEN position <= 4 THEN 1 ELSE 0 END) as top4s,
                  SUM(CASE WHEN position <= 8 THEN 1 ELSE 0 END) as top8s,
                  ROUND(SUM(CASE WHEN position <= 8 THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100, 1) as top8_pct,
                  COUNT(DISTINCT archetype) as arquetipos,
                  MIN(date) as primera, MAX(date) as ultima
           FROM decks
           WHERE date >= ? AND date <= ?{extra} AND total_players >= ?
           GROUP BY player_name
           HAVING entradas >= 3
           ORDER BY top4s DESC, victorias DESC
           LIMIT 50""",
        get_connection(), params=params,
    )


@st.cache_data(ttl=3600)
def load_player_history(name_query):
    return pd.read_sql_query(
        """SELECT d.player_name, d.archetype, d.position, d.total_players,
                  t.name as tournament, d.date
           FROM decks d JOIN tournaments t ON d.tournament_id = t.id
           WHERE d.player_name LIKE ?
           ORDER BY d.date DESC""",
        get_connection(), params=[f"%{name_query}%"],
    )


# Player scatter overview
st.subheader("Especialistas vs Experimentadores")
scatter_df = load_leaderboard(filters["start_date"], filters["end_date"],
                               filters["source"], filters["min_size"])
if not scatter_df.empty:
    st.plotly_chart(player_scatter(scatter_df), use_container_width=True)

# Leaderboard
st.subheader("Leaderboard")
leaderboard = load_leaderboard(filters["start_date"], filters["end_date"],
                                filters["source"], filters["min_size"])
st.dataframe(leaderboard.rename(columns={
    "player_name": "Jugador", "entradas": "Entradas", "torneos": "Torneos",
    "victorias": "Victorias", "top4s": "Top 4", "top8s": "Top 8",
    "top8_pct": "Top 8 %", "arquetipos": "Arquetipos",
    "primera": "Primera", "ultima": "Última",
}), use_container_width=True, hide_index=True)

# Player search
st.subheader("Buscar Jugador")
player_search = st.text_input("Nombre de jugador")
if player_search:
    player_data = load_player_history(player_search)

    if not player_data.empty:
        player_name = player_data["player_name"].iloc[0]
        st.markdown(f"### {player_name}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Entradas", len(player_data))
        col2.metric("Arquetipos", player_data["archetype"].nunique())
        col3.metric("Victorias", len(player_data[player_data["position"] == 1]))
        col4.metric("Top 8", len(player_data[player_data["position"] <= 8]))

        st.markdown("**Arquetipos favoritos:**")
        arch_counts = player_data["archetype"].value_counts().head(5).reset_index()
        arch_counts.columns = ["Arquetipo", "Entradas"]
        fig_arch = px.bar(arch_counts, x="Arquetipo", y="Entradas",
                          color="Arquetipo", title="Top 5 arquetipos")
        fig_arch.update_layout(showlegend=False)
        st.plotly_chart(fig_arch, use_container_width=True)

        st.markdown("**Historial completo:**")
        st.dataframe(player_data.rename(columns={
            "player_name": "Jugador", "archetype": "Arquetipo",
            "position": "Pos", "total_players": "Total",
            "tournament": "Torneo", "date": "Fecha",
        }), use_container_width=True, hide_index=True)
    else:
        st.info("Jugador no encontrado.")
