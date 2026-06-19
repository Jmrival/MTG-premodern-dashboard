import sqlite3

import pandas as pd


def get_mana_curve(conn: sqlite3.Connection, archetype: str,
                   start_date=None, end_date=None, source=None, min_size=1,
                   country=None) -> dict:
    """Average mana curve for an archetype's mainboard across filtered decks.

    Mana cost is summed regardless of color (e.g. "2RR" = 4 total mana), which is
    exactly what Scryfall's `cmc` field already represents.

    Returns dict with:
      - curve: DataFrame[bucket (int 0-6, 6 means "6+"), avg_copies]
      - avg_lands: float, average Land count per deck
      - avg_cmc: float or None, quantity-weighted average CMC of non-land mainboard cards
      - total_decks: int, decks included in the average
    """
    conditions = ["d.archetype = ?", "dc.is_sideboard = 0"]
    params = [archetype]
    if start_date:
        conditions.append("d.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("d.date <= ?")
        params.append(end_date)
    if source and source != "all":
        conditions.append("d.tournament_id IN (SELECT id FROM tournaments WHERE source = ?)")
        params.append(source)
    if country and country != "all":
        conditions.append("d.tournament_id IN (SELECT id FROM tournaments WHERE country = ?)")
        params.append(country)
    if min_size and min_size > 1:
        conditions.append("d.total_players >= ?")
        params.append(min_size)
    where = " AND ".join(conditions)

    total_decks = conn.execute(
        f"""SELECT COUNT(DISTINCT dc.deck_id)
            FROM deck_cards dc JOIN decks d ON dc.deck_id = d.id
            WHERE {where}""",
        params,
    ).fetchone()[0]

    empty = {"curve": pd.DataFrame(columns=["bucket", "avg_copies"]),
             "avg_lands": 0.0, "avg_cmc": None, "total_decks": 0}
    if total_decks == 0:
        return empty

    rows = pd.read_sql_query(
        f"""SELECT c.card_type, c.cmc, SUM(dc.quantity) AS total_qty
            FROM deck_cards dc
            JOIN decks d ON dc.deck_id = d.id
            JOIN cards c ON c.name = dc.card_name
            WHERE {where}
            GROUP BY c.card_type, c.cmc""",
        conn, params=params,
    )

    lands_qty = rows.loc[rows["card_type"] == "Land", "total_qty"].sum()
    nonland = rows[(rows["card_type"] != "Land") & rows["cmc"].notna()].copy()

    if nonland.empty:
        avg_cmc = None
        curve = pd.DataFrame({"bucket": range(0, 7), "avg_copies": [0.0] * 7})
    else:
        avg_cmc = (nonland["cmc"] * nonland["total_qty"]).sum() / nonland["total_qty"].sum()
        nonland["bucket"] = nonland["cmc"].clip(upper=6).astype(int)
        grouped = nonland.groupby("bucket")["total_qty"].sum()
        grouped = grouped.reindex(range(0, 7), fill_value=0)
        curve = grouped.reset_index()
        curve.columns = ["bucket", "total_qty"]
        curve["avg_copies"] = curve["total_qty"] / total_decks
        curve = curve[["bucket", "avg_copies"]]

    return {
        "curve": curve,
        "avg_lands": lands_qty / total_decks,
        "avg_cmc": avg_cmc,
        "total_decks": total_decks,
    }
