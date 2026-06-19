"""Prototipo: Grafo de co-ocurrencia de cartas MTG Premodern.

Correr con:
    streamlit run experiments/card_network.py

Lee la DB directamente. No forma parte del dashboard principal.
"""
import sqlite3
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.card_cooccurrence import (
    compute_pmi,
    compute_raw_cooccurrence,
    build_card_matrix,
    get_top_pairs,
)

st.set_page_config(page_title="Card Network — MTG Premodern", layout="wide")
st.title("Red de Co-ocurrencia de Cartas")

# ── Sidebar ──────────────────────────────────────────────────────────────────
ALL_CARD_TYPES = ["Creature", "Instant", "Sorcery", "Enchantment", "Artifact", "Land", "Planeswalker", "Others"]

with st.sidebar:
    db_path = st.text_input("Ruta a la DB", value="db/premodern.db")
    if not Path(db_path).exists():
        st.error(f"No se encontró: {db_path}")
        st.stop()

    conn_meta = sqlite3.connect(db_path)

    st.subheader("Métrica")
    metric = st.radio("Vínculo", ["PMI", "Conteo de mazos"], index=0, label_visibility="collapsed")

    st.subheader("Cartas a incluir")
    exclude_basics = st.checkbox("Excluir tierras básicas", value=True)
    include_side = st.checkbox("Incluir sideboard", value=False)

    selected_types = st.multiselect(
        "Filtrar por tipo de carta",
        options=ALL_CARD_TYPES,
        default=[],
        placeholder="Todos los tipos",
    )
    card_types_filter = selected_types if selected_types else None

    st.subheader("Arquetipo")
    archetypes = [r[0] for r in conn_meta.execute(
        "SELECT DISTINCT archetype FROM decks WHERE archetype IS NOT NULL ORDER BY archetype"
    ).fetchall()]
    selected_arch = st.selectbox("Arquetipo", ["Todos"] + archetypes)
    archetype_filter = None if selected_arch == "Todos" else selected_arch

    st.subheader("Parámetros")
    min_decks = st.slider("Mínimo de mazos por carta", 5, 100, 20, step=5)
    top_n = st.slider("Top N pares a mostrar", 10, 150, 50, step=10)
    if metric == "PMI":
        threshold = st.slider("Umbral mínimo (PMI)", 0.0, 5.0, 1.0, step=0.1)
    else:
        threshold = st.slider("Umbral mínimo (mazos compartidos)", 1, 500, 10, step=5)

    conn_meta.close()


# ── Carga y cómputo ──────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_network(db_path, metric, archetype, include_side, exclude_basics,
                 card_types, min_decks, threshold, top_n):
    conn = sqlite3.connect(db_path)

    matrix, valid_cards = build_card_matrix(
        conn,
        min_decks=min_decks,
        include_sideboard=include_side,
        archetype=archetype,
        card_types=list(card_types) if card_types else None,
        exclude_basic_lands=exclude_basics,
    )

    if matrix.empty or len(valid_cards) < 2:
        conn.close()
        return None, None, None

    if metric == "PMI":
        score_matrix = compute_pmi(matrix, top_n=min(500, len(valid_cards)))
    else:
        score_matrix = compute_raw_cooccurrence(matrix)

    pairs = get_top_pairs(score_matrix, n=top_n)
    pairs = pairs.rename(columns={"pmi": "weight"})
    pairs = pairs[pairs["weight"] >= threshold]

    pop_df = pd.read_sql_query(
        "SELECT card_name, deck_count FROM v_card_popularity", conn
    )
    popularity = dict(zip(pop_df["card_name"], pop_df["deck_count"]))

    conn.close()
    return pairs, popularity, valid_cards


# card_types must be hashable for cache — convert list to tuple
cache_types = tuple(sorted(selected_types)) if selected_types else ()

pairs, popularity, valid_cards = load_network(
    db_path, metric, archetype_filter, include_side, exclude_basics,
    cache_types, min_decks, threshold, top_n,
)

if pairs is None or pairs.empty:
    st.warning("No hay suficientes datos con los filtros actuales. Probá reducir los umbrales o ampliar los tipos de carta.")
    st.stop()


# ── Grafo con NetworkX + layout force-directed ────────────────────────────────
def build_figure(pairs_df: pd.DataFrame, popularity: dict) -> go.Figure:
    G = nx.Graph()
    for _, row in pairs_df.iterrows():
        G.add_edge(row["card_a"], row["card_b"], weight=float(row["weight"]))

    pos = nx.spring_layout(G, weight="weight", seed=42, k=1.5)

    weights = [d["weight"] for _, _, d in G.edges(data=True)]
    w_min, w_max = min(weights), max(weights)
    w_range = w_max - w_min if w_max != w_min else 1

    edge_traces = []
    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        norm_w = (data["weight"] - w_min) / w_range
        width = 0.5 + norm_w * 3.5
        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(width=width, color="rgba(150,150,150,0.5)"),
            hoverinfo="none",
            showlegend=False,
        ))

    nodes = list(G.nodes())
    node_x = [pos[n][0] for n in nodes]
    node_y = [pos[n][1] for n in nodes]

    max_pop = max((popularity.get(n, 1) for n in nodes), default=1)
    node_sizes = [8 + 22 * (popularity.get(n, 1) / max_pop) for n in nodes]

    node_hover = [
        f"<b>{n}</b><br>Mazos: {popularity.get(n, '?')}<br>Conexiones: {G.degree(n)}"
        for n in nodes
    ]

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=nodes,
        textposition="top center",
        textfont=dict(size=9),
        marker=dict(
            size=node_sizes,
            color="#3d8bcd",
            line=dict(width=1, color="white"),
        ),
        hovertext=node_hover,
        hoverinfo="text",
        showlegend=False,
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        height=700,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


n_cards = len(set(pairs["card_a"]) | set(pairs["card_b"]))
caption_parts = [
    f"{len(pairs)} pares · {n_cards} cartas únicas",
    f"Arquetipo: {selected_arch}" if selected_arch != "Todos" else "Todos los arquetipos",
    "Con sideboard" if include_side else "Solo mainboard",
    "Sin tierras básicas" if exclude_basics else "Con tierras básicas",
]
if selected_types:
    caption_parts.append("Tipos: " + ", ".join(selected_types))
st.caption(" · ".join(caption_parts))

fig = build_figure(pairs, popularity)
st.plotly_chart(fig, use_container_width=True)


# ── Top pares ─────────────────────────────────────────────────────────────────
with st.expander("Top pares por vínculo"):
    display = pairs.copy()
    display["weight"] = display["weight"].round(3)
    display.columns = ["Carta A", "Carta B", metric]
    st.dataframe(display, use_container_width=True, hide_index=True)


# ── Cartas más conectadas ─────────────────────────────────────────────────────
st.subheader("Cartas más conectadas")
G_degree = nx.Graph()
for _, row in pairs.iterrows():
    G_degree.add_edge(row["card_a"], row["card_b"], weight=float(row["weight"]))

degree_df = pd.DataFrame([
    {"Carta": n, "Conexiones": G_degree.degree(n), "Mazos": popularity.get(n, "?")}
    for n in G_degree.nodes()
]).sort_values("Conexiones", ascending=False).head(10)

st.dataframe(degree_df, use_container_width=True, hide_index=True)
