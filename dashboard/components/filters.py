import streamlit as st
import sqlite3
import pandas as pd


def get_db_connection(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(db_path, check_same_thread=False)


def sidebar_filters(conn: sqlite3.Connection) -> dict:
    """Render sidebar filters inside a form and return filter dict."""
    st.sidebar.header("Filtros")

    date_range = conn.execute(
        "SELECT MIN(date), MAX(date) FROM tournaments"
    ).fetchone()
    min_date = pd.to_datetime(date_range[0]) if date_range[0] else pd.Timestamp("2018-01-01")
    max_date = pd.to_datetime(date_range[1]) if date_range[1] else pd.Timestamp.now()
    default_start = max(min_date, max_date - pd.DateOffset(months=3))

    archetypes = pd.read_sql_query(
        "SELECT DISTINCT archetype FROM decks ORDER BY archetype", conn
    )["archetype"].tolist()

    with st.sidebar.form("filtros"):
        dates = st.date_input(
            "Rango de fechas",
            value=(default_start, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        if len(dates) == 2:
            start_date, end_date = dates
        else:
            start_date, end_date = default_start, max_date

        source = st.selectbox(
            "Fuente",
            ["all", "paper", "webcam", "mol"],
            format_func=lambda x: {"all": "Todas", "paper": "Paper",
                                    "webcam": "Webcam", "mol": "MTGO"}.get(x, x),
        )

        country_rows = conn.execute(
            """SELECT DISTINCT country FROM tournaments
               WHERE country IS NOT NULL AND country != 'Unknown'
               ORDER BY country"""
        ).fetchall()
        country_options = ["all"] + [r[0] for r in country_rows]
        country = st.selectbox(
            "País",
            country_options,
            format_func=lambda x: "Todos" if x == "all" else x,
        )

        min_size = st.slider("Tamaño mínimo torneo", 1, 200, 8)

        selected_archetypes = st.multiselect("Arquetipos", archetypes, default=[])

        st.form_submit_button("🔄 Actualizar", use_container_width=True)

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "source": source,
        "country": country,
        "min_size": min_size,
        "archetypes": selected_archetypes,
    }


def apply_filters(query: str, filters: dict) -> tuple[str, list]:
    """Append WHERE clauses to a query based on filters."""
    conditions = []
    params = []

    conditions.append("d.date >= ?")
    params.append(filters["start_date"])
    conditions.append("d.date <= ?")
    params.append(filters["end_date"])

    if filters["source"] != "all":
        conditions.append(
            "d.tournament_id IN (SELECT id FROM tournaments WHERE source = ?)"
        )
        params.append(filters["source"])

    if filters["min_size"] > 1:
        conditions.append("d.total_players >= ?")
        params.append(filters["min_size"])

    if filters["archetypes"]:
        placeholders = ",".join(["?"] * len(filters["archetypes"]))
        conditions.append(f"d.archetype IN ({placeholders})")
        params.extend(filters["archetypes"])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    return query, params
