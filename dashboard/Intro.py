import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.db import get_connection

st.set_page_config(
    page_title="MTG Premodern Analytics",
    page_icon="🃏",
    layout="wide",
    initial_sidebar_state="expanded",
)

conn = get_connection()

st.title("MTG Premodern Analytics")

col1, col2, col3, col4 = st.columns(4)
with col1:
    total_t = conn.execute("SELECT COUNT(*) FROM tournaments").fetchone()[0]
    st.metric("Torneos", f"{total_t:,}")
with col2:
    total_d = conn.execute("SELECT COUNT(*) FROM decks").fetchone()[0]
    st.metric("Mazos", f"{total_d:,}")
with col3:
    total_p = conn.execute("SELECT COUNT(DISTINCT player_name) FROM decks").fetchone()[0]
    st.metric("Jugadores", f"{total_p:,}")
with col4:
    total_c = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    st.metric("Cartas Únicas", f"{total_c:,}")

date_range = conn.execute("SELECT MIN(date), MAX(date) FROM tournaments").fetchone()
last_update = conn.execute("SELECT MAX(created_at) FROM decks").fetchone()[0]
caption = f"Datos desde {date_range[0]} hasta {date_range[1]}"
if last_update:
    caption += f" • Última actualización: {last_update}"
st.caption(caption)

st.markdown("---")

# Mini charts
mini_col1, mini_col2 = st.columns(2)

with mini_col1:
    top_arch = pd.read_sql_query(
        "SELECT archetype, COUNT(*) as mazos FROM decks GROUP BY archetype ORDER BY mazos DESC LIMIT 10",
        conn,
    )
    if not top_arch.empty:
        fig_arch = px.bar(
            top_arch, x="archetype", y="mazos",
            title="Top 10 Arquetipos",
            labels={"archetype": "Arquetipo", "mazos": "Mazos"},
        )
        fig_arch.update_layout(xaxis_tickangle=-30, height=300,
                               margin=dict(t=40, b=60, l=40, r=10))
        st.plotly_chart(fig_arch, width="stretch")

with mini_col2:
    monthly = pd.read_sql_query(
        "SELECT strftime('%Y-%m', date) as mes, COUNT(*) as mazos FROM decks GROUP BY mes ORDER BY mes",
        conn,
    )
    if not monthly.empty:
        fig_monthly = px.line(
            monthly, x="mes", y="mazos",
            title="Actividad por Mes",
            labels={"mes": "Mes", "mazos": "Mazos"},
        )
        fig_monthly.update_layout(height=300, margin=dict(t=40, b=60, l=40, r=10))
        st.plotly_chart(fig_monthly, width="stretch")

st.markdown("---")
st.markdown(
    "Navegá por las páginas en el sidebar para explorar el metagame, "
    "arquetipos, cartas, jugadores y análisis de posibles tendencias y predicciones.\n\n"
    "Usá los filtros en el sidebar para ajustar el periodo, la fuente y la región que te interese."
)
