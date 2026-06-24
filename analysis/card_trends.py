import pandas as pd
import numpy as np
import sqlite3
from scipy import stats


def get_card_adoption(conn: sqlite3.Connection,
                      sideboard: bool = False,
                      start_date=None, end_date=None,
                      source=None, min_size=None,
                      country=None, archetypes=None) -> pd.DataFrame:
    """Monthly adoption rate per card (% of decks playing it)."""
    sb_filter = 1 if sideboard else 0
    extra = ""
    params = []
    if start_date:
        extra += " AND d.date >= ?"
        params.append(start_date)
    if end_date:
        extra += " AND d.date <= ?"
        params.append(end_date)
    if source and source != "all":
        extra += " AND d.tournament_id IN (SELECT id FROM tournaments WHERE source = ?)"
        params.append(source)
    if country and country != "all":
        extra += " AND d.tournament_id IN (SELECT id FROM tournaments WHERE country = ?)"
        params.append(country)
    if min_size and min_size > 1:
        extra += " AND d.total_players >= ?"
        params.append(min_size)
    if archetypes:
        placeholders = ",".join(["?"] * len(archetypes))
        extra += f" AND d.archetype IN ({placeholders})"
        params.extend(archetypes)

    df = pd.read_sql_query(
        f"""SELECT dc.card_name, strftime('%Y-%m', d.date) as month,
                   COUNT(DISTINCT dc.deck_id) as deck_count
            FROM deck_cards dc
            JOIN decks d ON dc.deck_id = d.id
            WHERE dc.is_sideboard = {sb_filter}{extra}
            GROUP BY dc.card_name, month""",
        conn, params=params,
    )

    monthly_totals = pd.read_sql_query(
        f"""SELECT strftime('%Y-%m', d.date) as month, COUNT(*) as total
           FROM decks d WHERE 1=1{extra}
           GROUP BY month""",
        conn, params=params,
    )

    df = df.merge(monthly_totals, on="month")
    df["adoption_pct"] = (df["deck_count"] / df["total"] * 100).round(2)

    return df


def detect_trends(conn: sqlite3.Connection, window_months: int = 6,
                  min_decks: int = 20, start_date=None, end_date=None,
                  source=None, min_size=None, country=None, archetypes=None) -> pd.DataFrame:
    """Detect rising and falling cards via linear regression."""
    df = get_card_adoption(conn, start_date=start_date, end_date=end_date,
                           source=source, min_size=min_size, country=country, archetypes=archetypes)

    card_counts = df.groupby("card_name")["deck_count"].sum()
    valid_cards = card_counts[card_counts >= min_decks].index

    months = sorted(df["month"].unique())
    recent_months = months[-window_months:] if len(months) >= window_months else months

    recent = df[df["month"].isin(recent_months) & df["card_name"].isin(valid_cards)]

    trends = []
    for card_name, group in recent.groupby("card_name"):
        if len(group) < 3:
            continue

        x = np.arange(len(group))
        y = group["adoption_pct"].values
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        trends.append({
            "card_name": card_name,
            "slope": round(slope, 4),
            "r_squared": round(r_value ** 2, 4),
            "p_value": round(p_value, 4),
            "current_adoption": y[-1],
            "direction": "rising" if slope > 0 else "falling",
        })

    result = pd.DataFrame(trends)
    result["significant"] = result["p_value"] < 0.05
    return result.sort_values("slope", ascending=False)


def get_breakout_cards(conn: sqlite3.Connection, std_threshold: float = 3.0,
                       start_date=None, end_date=None,
                       source=None, min_size=None, country=None, archetypes=None) -> pd.DataFrame:
    """Find cards with adoption spikes beyond N standard deviations."""
    df = get_card_adoption(conn, start_date=start_date, end_date=end_date,
                           source=source, min_size=min_size, country=country, archetypes=archetypes)

    card_stats = df.groupby("card_name")["adoption_pct"].agg(["mean", "std"]).reset_index()
    card_stats.columns = ["card_name", "mean_adoption", "std_adoption"]
    card_stats = card_stats[card_stats["std_adoption"] > 0]

    latest_month = df["month"].max()
    latest = df[df["month"] == latest_month][["card_name", "adoption_pct"]]

    merged = latest.merge(card_stats, on="card_name")
    merged["z_score"] = (merged["adoption_pct"] - merged["mean_adoption"]) / merged["std_adoption"]
    breakouts = merged[merged["z_score"] > std_threshold].sort_values("z_score", ascending=False)

    return breakouts
