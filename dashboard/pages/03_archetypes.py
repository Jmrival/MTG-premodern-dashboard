import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dashboard.db import get_connection
from dashboard.components.filters import sidebar_filters
from dashboard.components.charts import evolution_line, mana_curve_bar

conn = get_connection()

st.header("Arquetipos - Deep Dive")
filters = sidebar_filters(conn)


@st.cache_data(ttl=3600)
def load_archetypes():
    return pd.read_sql_query(
        "SELECT archetype, COUNT(*) as cnt FROM decks GROUP BY archetype ORDER BY cnt DESC",
        get_connection(),
    )


def _filter_clause(start_date, end_date, source, min_size, alias="d", country=None):
    """Build extra WHERE clause + params for date/source/country/min_size filters."""
    clause = f" AND {alias}.date >= ? AND {alias}.date <= ?"
    params = [start_date, end_date]
    if source and source != "all":
        clause += f" AND {alias}.tournament_id IN (SELECT id FROM tournaments WHERE source = ?)"
        params.append(source)
    if country and country != "all":
        clause += f" AND {alias}.tournament_id IN (SELECT id FROM tournaments WHERE country = ?)"
        params.append(country)
    if min_size and min_size > 1:
        clause += f" AND {alias}.total_players >= ?"
        params.append(min_size)
    return clause, params


@st.cache_data(ttl=3600)
def load_archetype_stats(archetype, start_date, end_date, source, min_size, country="all"):
    extra, params = _filter_clause(start_date, end_date, source, min_size, "decks", country)
    row = get_connection().execute(
        f"""SELECT COUNT(*) as entries,
                  AVG(CASE WHEN position <= 4 THEN 1.0 ELSE 0.0 END) as top4_rate,
                  MIN(date) as first_seen, MAX(date) as last_seen
           FROM decks WHERE archetype = ?{extra}""",
        [archetype] + params,
    ).fetchone()
    return tuple(row) if row else (0, None, None, None)


@st.cache_data(ttl=3600)
def load_card_sections(archetype, start_date, end_date, source, min_size, country="all"):
    c = get_connection()
    extra, params = _filter_clause(start_date, end_date, source, min_size, "d", country)

    total_decks_arch = c.execute(
        f"""SELECT COUNT(*) FROM decks d
            WHERE d.archetype = ? AND d.cards_scraped = 1{extra}""",
        [archetype] + params,
    ).fetchone()[0]

    if total_decks_arch == 0:
        return None, None, None, total_decks_arch

    success_expr = """
                  ROUND(AVG(CASE WHEN d.position <= 8 THEN 1.0
                                 WHEN d.position IS NOT NULL THEN 0.0 END) * 100, 1) as top8_pct,
                  ROUND(AVG(CASE WHEN d.position <= 4 THEN 1.0
                                 WHEN d.position IS NOT NULL THEN 0.0 END) * 100, 1) as top4_pct,
                  ROUND(AVG(CASE WHEN d.position = 1 THEN 1.0
                                 WHEN d.position IS NOT NULL THEN 0.0 END) * 100, 1) as top1_pct"""

    core = pd.read_sql_query(
        f"""SELECT dc.card_name, COUNT(DISTINCT dc.deck_id) as decks,
                  ROUND(AVG(dc.quantity), 1) as avg_qty,
                  ROUND(COUNT(DISTINCT dc.deck_id) * 100.0 / ?, 1) as pct,
                  {success_expr},
                  MAX(c.price_usd) as price_usd
           FROM deck_cards dc JOIN decks d ON dc.deck_id = d.id
           JOIN cards c ON c.name = dc.card_name
           WHERE d.archetype = ? AND dc.is_sideboard = 0{extra}
           GROUP BY dc.card_name HAVING pct > 75 ORDER BY pct DESC""",
        c, params=[total_decks_arch, archetype] + params,
    )
    flex = pd.read_sql_query(
        f"""SELECT dc.card_name, COUNT(DISTINCT dc.deck_id) as decks,
                  ROUND(AVG(dc.quantity), 1) as avg_qty,
                  ROUND(COUNT(DISTINCT dc.deck_id) * 100.0 / ?, 1) as pct,
                  {success_expr},
                  MAX(c.price_usd) as price_usd
           FROM deck_cards dc JOIN decks d ON dc.deck_id = d.id
           JOIN cards c ON c.name = dc.card_name
           WHERE d.archetype = ? AND dc.is_sideboard = 0{extra}
           GROUP BY dc.card_name HAVING pct BETWEEN 25 AND 75 ORDER BY pct DESC""",
        c, params=[total_decks_arch, archetype] + params,
    )
    sb = pd.read_sql_query(
        f"""SELECT dc.card_name, COUNT(DISTINCT dc.deck_id) as decks,
                  ROUND(AVG(dc.quantity), 1) as avg_qty,
                  {success_expr},
                  MAX(c.price_usd) as price_usd
           FROM deck_cards dc JOIN decks d ON dc.deck_id = d.id
           JOIN cards c ON c.name = dc.card_name
           WHERE d.archetype = ? AND dc.is_sideboard = 1{extra}
           GROUP BY dc.card_name ORDER BY decks DESC LIMIT 20""",
        c, params=[archetype] + params,
    )
    return core, flex, sb, total_decks_arch


@st.cache_data(ttl=3600)
def load_breakthrough_cards(archetype, start_date, end_date, source, min_size, country="all"):
    """Cards with low overall adoption but high recent success within the filtered window."""
    c = get_connection()
    extra, params = _filter_clause(start_date, end_date, source, min_size, "d", country)

    total_decks_arch = c.execute(
        f"""SELECT COUNT(*) FROM decks d
            WHERE d.archetype = ? AND d.cards_scraped = 1{extra}""",
        [archetype] + params,
    ).fetchone()[0]

    if total_decks_arch == 0:
        return pd.DataFrame()

    return pd.read_sql_query(
        f"""SELECT dc.card_name, COUNT(DISTINCT dc.deck_id) as decks,
                  ROUND(COUNT(DISTINCT dc.deck_id) * 100.0 / ?, 1) as pct,
                  ROUND(AVG(CASE WHEN d.position <= 8 THEN 1.0
                                 WHEN d.position IS NOT NULL THEN 0.0 END) * 100, 1) as top8_pct,
                  ROUND(AVG(CASE WHEN d.position <= 4 THEN 1.0
                                 WHEN d.position IS NOT NULL THEN 0.0 END) * 100, 1) as top4_pct,
                  ROUND(AVG(CASE WHEN d.position = 1 THEN 1.0
                                 WHEN d.position IS NOT NULL THEN 0.0 END) * 100, 1) as top1_pct
           FROM deck_cards dc JOIN decks d ON dc.deck_id = d.id
           WHERE d.archetype = ? AND dc.is_sideboard = 0{extra}
           GROUP BY dc.card_name
           HAVING pct <= 25 AND decks >= 3 AND top8_pct >= 50
           ORDER BY top8_pct DESC, decks DESC
           LIMIT 15""",
        c, params=[total_decks_arch, archetype] + params,
    )


@st.cache_data(ttl=3600)
def load_mana_curve(archetype, start_date, end_date, source, min_size, country="all"):
    from analysis.mana_curve import get_mana_curve
    return get_mana_curve(get_connection(), archetype,
                          start_date=start_date, end_date=end_date,
                          source=source, min_size=min_size, country=country)


@st.cache_data(ttl=3600)
def load_deck_prices(archetype, start_date, end_date, source, min_size, country="all"):
    """Average deck price (main, side, total) across filtered decks with price data."""
    c = get_connection()
    extra, params = _filter_clause(start_date, end_date, source, min_size, "d", country)
    row = c.execute(
        f"""SELECT
              AVG(total_usd)   AS avg_total,
              AVG(main_usd)    AS avg_main,
              AVG(side_usd)    AS avg_side
            FROM (
              SELECT
                d.id,
                SUM(dc.quantity * COALESCE(c.price_usd, 0))                              AS total_usd,
                SUM(CASE WHEN dc.is_sideboard=0 THEN dc.quantity * COALESCE(c.price_usd,0) ELSE 0 END) AS main_usd,
                SUM(CASE WHEN dc.is_sideboard=1 THEN dc.quantity * COALESCE(c.price_usd,0) ELSE 0 END) AS side_usd
              FROM decks d
              JOIN deck_cards dc ON dc.deck_id = d.id
              JOIN cards c ON c.name = dc.card_name
              WHERE d.archetype = ? AND d.cards_scraped = 1{extra}
              GROUP BY d.id
              HAVING SUM(COALESCE(c.price_usd, 0)) > 0
            )""",
        [archetype] + params,
    ).fetchone()
    return tuple(row) if row else (None, None, None)


@st.cache_data(ttl=3600)
def load_recent_results(archetype, start_date, end_date, source, min_size, country="all"):
    extra, params = _filter_clause(start_date, end_date, source, min_size, "d", country)
    return pd.read_sql_query(
        f"""SELECT d.player_name, d.position, d.total_players, t.name, d.date,
                  ROUND(SUM(dc.quantity * COALESCE(c.price_usd, 0)), 2) AS valor_usd
           FROM decks d
           JOIN tournaments t ON d.tournament_id = t.id
           LEFT JOIN deck_cards dc ON dc.deck_id = d.id
           LEFT JOIN cards c ON c.name = dc.card_name
           WHERE d.archetype = ?{extra}
           GROUP BY d.id, d.player_name, d.position, d.total_players, t.name, d.date
           ORDER BY d.date DESC LIMIT 20""",
        get_connection(), params=[archetype] + params,
    )


archetypes = load_archetypes()
selected = st.selectbox("Arquetipo", archetypes["archetype"].tolist())

if selected:
    f_args = (filters["start_date"], filters["end_date"], filters["source"], filters["min_size"], filters.get("country", "all"))
    stats = load_archetype_stats(selected, *f_args)

    prices = load_deck_prices(selected, *f_args)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Entradas", f"{stats[0]:,}")
    col2.metric("Tasa Top 4", f"{stats[1]:.1%}" if stats[1] else "N/A")
    col3.metric("Primera aparición", stats[2])
    col4.metric("Última aparición", stats[3])

    pc1, pc2, pc3 = st.columns(3)
    pc1.metric("Precio promedio mazo", f"${prices[0]:.0f}" if prices[0] else "N/A",
               help="Main deck + sideboard · versión más económica por carta")
    pc2.metric("Precio promedio main deck", f"${prices[1]:.0f}" if prices[1] else "N/A")
    pc3.metric("Precio promedio sideboard", f"${prices[2]:.0f}" if prices[2] else "N/A")

    # Win rate evolution line chart
    try:
        from analysis.success_metrics import get_archetype_success_over_time

        @st.cache_data(ttl=3600)
        def load_evolution(archetype, start_date, end_date, source):
            return get_archetype_success_over_time(
                get_connection(), archetype,
                min_date=start_date, max_date=end_date, source=source,
            )

        evo = load_evolution(selected, filters["start_date"], filters["end_date"], filters["source"])
        if evo is not None and not evo.empty:
            st.plotly_chart(evolution_line(evo, selected), use_container_width=True)
    except Exception:
        pass

    has_cards = conn.execute(
        "SELECT COUNT(*) FROM deck_cards dc JOIN decks d ON dc.deck_id = d.id WHERE d.archetype = ?",
        (selected,),
    ).fetchone()[0]

    # Mana Curve
    if has_cards > 0:
        st.subheader("Mana Curve")
        try:
            curve_data = load_mana_curve(selected, *f_args)
            if curve_data["total_decks"] == 0:
                st.info("No hay mazos con cartas scrapeadas para el período/filtros seleccionados.")
            elif curve_data["avg_cmc"] is None:
                st.info(
                    "Las cartas todavía no tienen coste de maná cargado. "
                    "Corré el backfill de Scryfall (notebook 02/03) y volvé a subir la base."
                )
            else:
                st.plotly_chart(
                    mana_curve_bar(
                        curve_data["curve"], curve_data["avg_lands"],
                        curve_data["avg_cmc"], selected,
                    ),
                    use_container_width=True,
                )
                st.caption(
                    f"Promedio sobre {curve_data['total_decks']:,} mazos · "
                    f"Tierras promedio: {curve_data['avg_lands']:.1f}"
                )
        except Exception as e:
            st.info(f"Mana Curve no disponible: {e}")

    success_col_config = {
        "% Mazos": st.column_config.ProgressColumn(
            "% Mazos", min_value=0, max_value=100, format="%.1f%%"
        ),
        "Top 8 %": st.column_config.ProgressColumn(
            "Top 8 %", min_value=0, max_value=100, format="%.1f%%"
        ),
        "Top 4 %": st.column_config.ProgressColumn(
            "Top 4 %", min_value=0, max_value=100, format="%.1f%%"
        ),
        "Top 1 %": st.column_config.ProgressColumn(
            "Top 1 %", min_value=0, max_value=100, format="%.1f%%"
        ),
        "Precio (USD)": st.column_config.NumberColumn(
            "Precio (USD)", format="$%.2f"
        ),
    }

    if has_cards > 0:
        core, flex, sb, total_decks_arch = load_card_sections(selected, *f_args)

        if total_decks_arch > 0:
            st.subheader("Core Cards (>75% de los mazos)")
            if core is not None and not core.empty:
                st.dataframe(
                    core.rename(columns={
                        "card_name": "Carta", "decks": "Mazos",
                        "avg_qty": "Promedio", "pct": "% Mazos",
                        "top8_pct": "Top 8 %", "top4_pct": "Top 4 %", "top1_pct": "Top 1 %",
                        "price_usd": "Precio (USD)",
                    }),
                    column_config=success_col_config,
                    use_container_width=True, hide_index=True,
                )

            st.subheader("Flex Slots (25-75%)")
            if flex is not None and not flex.empty:
                st.dataframe(
                    flex.rename(columns={
                        "card_name": "Carta", "decks": "Mazos",
                        "avg_qty": "Promedio", "pct": "% Mazos",
                        "top8_pct": "Top 8 %", "top4_pct": "Top 4 %", "top1_pct": "Top 1 %",
                        "price_usd": "Precio (USD)",
                    }),
                    column_config=success_col_config,
                    use_container_width=True, hide_index=True,
                )

            st.subheader("Sideboard más común")
            if sb is not None and not sb.empty:
                st.dataframe(
                    sb.rename(columns={
                        "card_name": "Carta", "decks": "Mazos", "avg_qty": "Promedio",
                        "top8_pct": "Top 8 %", "top4_pct": "Top 4 %", "top1_pct": "Top 1 %",
                        "price_usd": "Precio (USD)",
                    }),
                    column_config=success_col_config,
                    use_container_width=True, hide_index=True,
                )
        else:
            st.info("No hay datos de cartas para el período/filtros seleccionados.")
    else:
        st.info("No hay datos de cartas para este arquetipo. Ejecutá el notebook 02 primero.")

    st.subheader("Últimos 20 resultados")
    recent = load_recent_results(selected, *f_args)
    st.dataframe(
        recent.rename(columns={
            "player_name": "Jugador", "position": "Pos", "total_players": "Total",
            "name": "Torneo", "date": "Fecha", "valor_usd": "Valor (USD)",
        }),
        column_config={
            "Valor (USD)": st.column_config.NumberColumn(
                "Valor (USD)", format="$%.0f"
            ),
        },
        use_container_width=True, hide_index=True,
    )

    # Breakthroughs: low-adoption cards with recent high success
    st.subheader("Breakthroughs / Novedades")
    if has_cards > 0:
        breakthroughs = load_breakthrough_cards(selected, *f_args)
        if not breakthroughs.empty:
            st.caption(
                "Cartas poco jugadas dentro del arquetipo (≤25% de adopción) que tuvieron "
                "alto rendimiento (Top 8 ≥ 50%) en el período/filtros seleccionados."
            )
            st.dataframe(
                breakthroughs.rename(columns={
                    "card_name": "Carta", "decks": "Mazos", "pct": "% Mazos",
                    "top8_pct": "Top 8 %", "top4_pct": "Top 4 %", "top1_pct": "Top 1 %",
                }),
                column_config=success_col_config,
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("No se detectaron breakthroughs con los filtros actuales.")
