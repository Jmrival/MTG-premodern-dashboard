import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.db import get_connection
from dashboard.components.filters import sidebar_filters
from dashboard.components.charts import meta_share_area, heatmap_meta
from analysis.meta_evolution import get_meta_share, get_meta_trend, detect_breakouts

conn = get_connection()

st.header("Evolución Temporal")
filters = sidebar_filters(conn)


@st.cache_data(ttl=3600)
def load_meta_share(start_date, end_date, source, min_size, country="all", archetypes=()):
    return get_meta_share(get_connection(), min_date=start_date, max_date=end_date,
                          source=source, min_size=min_size, country=country,
                          archetypes=archetypes if archetypes else None)


@st.cache_data(ttl=3600)
def load_meta_trend(start_date, end_date, source, min_size, country="all", archetypes=()):
    return get_meta_trend(get_connection(), min_date=start_date, max_date=end_date,
                          source=source, min_size=min_size, country=country,
                          archetypes=archetypes if archetypes else None)


@st.cache_data(ttl=3600)
def load_breakouts(start_date, end_date, source, min_size, country="all", archetypes=()):
    return detect_breakouts(get_connection(), min_date=start_date, max_date=end_date,
                            source=source, min_size=min_size, country=country,
                            archetypes=archetypes if archetypes else None)


meta_df = load_meta_share(filters["start_date"], filters["end_date"],
                           filters["source"], filters["min_size"],
                           filters.get("country", "all"), tuple(filters.get("archetypes", [])))

if meta_df.empty:
    st.warning("No hay datos para el rango seleccionado.")
    st.stop()

# Stacked area
top_n = st.slider("Top N arquetipos", 5, 25, 10)
st.plotly_chart(meta_share_area(meta_df, top_n=top_n), use_container_width=True)

# Heatmap
st.subheader("Heatmap Meta Share")
trend_df = load_meta_trend(filters["start_date"], filters["end_date"],
                           filters["source"], filters["min_size"],
                           filters.get("country", "all"), tuple(filters.get("archetypes", [])))
if not trend_df.empty:
    st.plotly_chart(heatmap_meta(trend_df, top_n=top_n), use_container_width=True)

# Breakouts
st.subheader("Breakouts Recientes")
breakouts = load_breakouts(filters["start_date"], filters["end_date"],
                           filters["source"], filters["min_size"],
                           filters.get("country", "all"), tuple(filters.get("archetypes", [])))
if not breakouts.empty:
    st.dataframe(
        breakouts.rename(columns={
            "month": "Mes", "archetype": "Arquetipo",
            "share_pct": "% Meta", "change_pct": "Cambio %",
        }).tail(20),
        use_container_width=True, hide_index=True,
    )
else:
    st.info("No se detectaron breakouts recientes.")

# Single archetype trend
st.subheader("Tendencia Individual")
archetypes = meta_df["archetype"].unique().tolist()
selected = st.selectbox("Seleccionar arquetipo", sorted(archetypes))
if selected:
    arch_data = meta_df[meta_df["archetype"] == selected]
    fig = px.line(arch_data, x="month", y="meta_share_pct",
                  title=f"Evolución de {selected}",
                  labels={"meta_share_pct": "% Meta", "month": "Mes"})
    st.plotly_chart(fig, use_container_width=True)
