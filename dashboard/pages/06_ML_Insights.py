import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.db import get_connection
from dashboard.components.charts import cooccurrence_network, forecast_line

conn = get_connection()

st.header("ML Insights")

has_cards = conn.execute("SELECT COUNT(*) FROM deck_cards").fetchone()[0]

# ── Meta Prediction ───────────────────────────────────────────────────────────
_INFO_FORECAST = """
**¿Cómo se calcula este forecast?**

Usa *Suavizado Exponencial de Holt-Winters* (tendencia aditiva amortiguada, sin estacionalidad).
El modelo analiza la serie histórica de % meta mensual de cada arquetipo y proyecta
los próximos 3 meses asignando más peso a los datos recientes.

**¿Qué tan confiable es?**

- Funciona bien para tendencias claras y sostenidas (un arquetipo en ascenso o caída).
- Es poco confiable ante cambios bruscos por bans, nuevas cartas o eventos puntuales.
- Requiere al menos 6 meses de historia por arquetipo; con menos datos el error aumenta.
- Tomarlo como una señal de dirección, no como un número exacto.
"""

col_title, col_info = st.columns([8, 1])
col_title.subheader("Predicción del Meta")
with col_info.popover("ℹ️"):
    st.markdown(_INFO_FORECAST)

try:
    from analysis.predictive import forecast_meta
    from analysis.meta_evolution import get_meta_share

    @st.cache_data(ttl=3600)
    def load_forecasts():
        return forecast_meta(get_connection())

    @st.cache_data(ttl=3600)
    def load_hist_meta():
        return get_meta_share(get_connection())

    forecasts = load_forecasts()
    if not forecasts.empty:
        hist_meta = load_hist_meta()
        if not hist_meta.empty:
            arch_in_forecast = forecasts["archetype"].unique()
            hist_filtered = hist_meta[hist_meta["archetype"].isin(arch_in_forecast)]

            # Temporal scale control
            all_months = sorted(hist_filtered["month"].unique())
            n_months = len(all_months)
            months_back = st.slider(
                "Meses de historia a mostrar",
                min_value=3,
                max_value=n_months,
                value=min(24, n_months),
                step=1,
            )
            cutoff = all_months[-months_back] if months_back < n_months else all_months[0]
            hist_window = hist_filtered[hist_filtered["month"] >= cutoff]

            st.plotly_chart(
                forecast_line(hist_window, forecasts),
                width="stretch",
            )
        st.dataframe(forecasts.rename(columns={
            "archetype": "Arquetipo", "period": "Período",
            "forecast_share": "% Predicho", "current_share": "% Actual",
        }), width="stretch", hide_index=True)
    else:
        st.info("No hay suficientes datos históricos para generar predicciones.")
except ImportError:
    st.info("statsmodels no está instalado. Ejecutá: pip install statsmodels")
except Exception as e:
    st.warning(f"Predicción no disponible: {e}")

if has_cards == 0:
    st.warning(
        "Las funciones de clustering y co-ocurrencia requieren datos de cartas. "
        "Ejecutá el notebook 02 primero."
    )
    st.stop()

# ── UMAP Clustering ───────────────────────────────────────────────────────────
st.subheader("Clustering de Mazos (UMAP + HDBSCAN)")
if st.button("Ejecutar Clustering (puede tardar ~1 min)"):
    with st.spinner("Calculando embeddings UMAP..."):
        try:
            from analysis.archetype_clustering import full_clustering_pipeline
            from dashboard.components.charts import umap_scatter
            result = full_clustering_pipeline(conn)
            if result is not None and not result.empty:
                st.plotly_chart(umap_scatter(result), width="stretch")
                n_clusters = result["cluster"].nunique() - (1 if -1 in result["cluster"].values else 0)
                noise = (result["cluster"] == -1).sum()
                st.caption(f"Clusters encontrados: {n_clusters} | Puntos sin cluster: {noise}")
            else:
                st.info("No hay suficientes datos para clustering.")
        except ImportError as e:
            st.error(f"Dependencia faltante: {e}. Ejecutá: pip install umap-learn hdbscan")
        except Exception as e:
            st.error(f"Error en clustering: {e}")

# ── Card Co-occurrence (PMI) ──────────────────────────────────────────────────
st.subheader("Co-ocurrencia de Cartas (PMI)")
try:
    from analysis.card_cooccurrence import compute_pmi, build_card_matrix, get_top_pairs

    @st.cache_data(ttl=3600)
    def load_pmi(min_decks, top_n):
        matrix, valid_cards = build_card_matrix(get_connection(), min_decks=min_decks)
        if len(valid_cards) <= 10:
            return None
        pmi_df = compute_pmi(matrix, top_n=200)
        return get_top_pairs(pmi_df, n=top_n)

    min_decks = st.slider("Mínimo de mazos por carta", 5, 50, 20)
    top_n_pairs = st.slider("Pares a mostrar en el grafo", 10, 50, 30)
    top_pairs = load_pmi(min_decks, top_n=top_n_pairs)

    if top_pairs is not None:
        st.plotly_chart(cooccurrence_network(top_pairs), width="stretch")
        with st.expander("Ver tabla de pares"):
            st.dataframe(top_pairs.rename(columns={
                "card_a": "Carta A", "card_b": "Carta B", "pmi": "PMI",
            }), width="stretch", hide_index=True)
    else:
        st.info("No hay suficientes datos para análisis de co-ocurrencia con ese mínimo.")
except ImportError as e:
    st.info(f"Dependencia faltante: {e}. Ejecutá: pip install networkx scipy")
except Exception as e:
    st.warning(f"Co-ocurrencia no disponible: {e}")

# ── Meta Reaction Model ───────────────────────────────────────────────────────
st.subheader("Modelo de Reacción del Meta")
archetypes = pd.read_sql_query(
    "SELECT archetype, COUNT(*) as cnt FROM decks GROUP BY archetype ORDER BY cnt DESC LIMIT 15",
    conn,
)["archetype"].tolist()

target = st.selectbox("Arquetipo objetivo", archetypes)
if target and st.button("Entrenar modelo"):
    with st.spinner("Entrenando Random Forest..."):
        try:
            from analysis.predictive import meta_reaction_model
            result = meta_reaction_model(conn, target)
            if "error" not in result:
                col1, col2 = st.columns(2)
                col1.metric("MAE (Error Absoluto Medio)", f"{result['mae']:.4f}")
                col2.metric("Predicción actual", f"{result['last_prediction']:.1f}%")
                st.markdown("**Features más importantes:**")
                fi = pd.DataFrame([
                    {"Feature": k, "Importancia": round(v, 4)}
                    for k, v in result["feature_importance"].items()
                ])
                st.dataframe(fi, hide_index=True)
            else:
                st.warning(result["error"])
        except ImportError as e:
            st.error(f"Dependencia faltante: {e}. Ejecutá: pip install scikit-learn statsmodels")
        except Exception as e:
            st.error(f"Error entrenando modelo: {e}")
