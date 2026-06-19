import pandas as pd
import numpy as np
import sqlite3
from scipy import stats


def get_card_adoption(conn: sqlite3.Connection,
                      sideboard: bool = False) -> pd.DataFrame:
    """Monthly adoption rate per card (% of decks playing it)."""
    sb_filter = 1 if sideboard else 0
    df = pd.read_sql_query(
        f"""SELECT dc.card_name, strftime('%Y-%m', d.date) as month,
                   COUNT(DISTINCT dc.deck_id) as deck_count
            FROM deck_cards dc
            JOIN decks d ON dc.deck_id = d.id
            WHERE dc.is_sideboard = {sb_filter}
            GROUP BY dc.card_name, month""",
        conn,
    )

    monthly_totals = pd.read_sql_query(
        """SELECT strftime('%Y-%m', date) as month, COUNT(*) as total
           FROM decks GROUP BY month""",
        conn,
    )

    df = df.merge(monthly_totals, on="month")
    df["adoption_pct"] = (df["deck_count"] / df["total"] * 100).round(2)

    return df


def detect_trends(conn: sqlite3.Connection, window_months: int = 6,
                  min_decks: int = 20) -> pd.DataFrame:
    """Detect rising and falling cards via linear regression."""
    df = get_card_adoption(conn)

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


def get_breakout_cards(conn: sqlite3.Connection, std_threshold: float = 3.0) -> pd.DataFrame:
    """Find cards with adoption spikes beyond N standard deviations."""
    df = get_card_adoption(conn)

    card_stats = df.groupby("card_name")["adoption_pct"].agg(["mean", "std"]).reset_index()
    card_stats.columns = ["card_name", "mean_adoption", "std_adoption"]
    card_stats = card_stats[card_stats["std_adoption"] > 0]

    latest_month = df["month"].max()
    latest = df[df["month"] == latest_month][["card_name", "adoption_pct"]]

    merged = latest.merge(card_stats, on="card_name")
    merged["z_score"] = (merged["adoption_pct"] - merged["mean_adoption"]) / merged["std_adoption"]
    breakouts = merged[merged["z_score"] > std_threshold].sort_values("z_score", ascending=False)

    return breakouts
