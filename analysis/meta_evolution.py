import pandas as pd
import sqlite3


def _base_decks_query(min_date=None, max_date=None, source=None, min_size=8):
    """Build the base WHERE clause for decks filtered by date, source, size."""
    conditions = ["1=1"]
    params = []

    if min_date:
        conditions.append("d.date >= ?")
        params.append(min_date)
    if max_date:
        conditions.append("d.date <= ?")
        params.append(max_date)
    if source and source != "all":
        conditions.append(
            "d.tournament_id IN (SELECT id FROM tournaments WHERE source = ?)"
        )
        params.append(source)
    if min_size and min_size > 1:
        conditions.append("d.total_players >= ?")
        params.append(min_size)

    return " AND ".join(conditions), params


def get_meta_share(conn: sqlite3.Connection, min_date=None, max_date=None,
                   source=None, min_size=1) -> pd.DataFrame:
    """Calculate monthly meta share % per archetype."""
    where, params = _base_decks_query(min_date, max_date, source, min_size)
    query = f"""
        SELECT d.archetype, strftime('%Y-%m', d.date) AS month, COUNT(*) AS deck_count
        FROM decks d
        WHERE {where}
        GROUP BY d.archetype, month ORDER BY month, deck_count DESC
    """
    df = pd.read_sql_query(query, conn, params=params)
    if df.empty:
        return df
    monthly_totals = df.groupby("month")["deck_count"].transform("sum")
    df["meta_share_pct"] = (df["deck_count"] / monthly_totals * 100).round(2)
    return df


def get_meta_trend(conn: sqlite3.Connection, window: int = 3,
                   min_date=None, max_date=None, source=None, min_size=1) -> pd.DataFrame:
    """Meta share with rolling average to smooth noise."""
    df = get_meta_share(conn, min_date=min_date, max_date=max_date,
                        source=source, min_size=min_size)
    if df.empty:
        return df
    pivot = df.pivot_table(index="month", columns="archetype",
                           values="meta_share_pct", fill_value=0)
    return pivot.rolling(window=window, min_periods=1).mean()


def detect_breakouts(conn: sqlite3.Connection, threshold: float = 50.0,
                     min_date=None, max_date=None, source=None, min_size=1) -> pd.DataFrame:
    """Find archetypes with >threshold% month-over-month share increase."""
    df = get_meta_share(conn, min_date=min_date, max_date=max_date,
                        source=source, min_size=min_size)
    if df.empty:
        return pd.DataFrame()
    pivot = df.pivot_table(index="month", columns="archetype",
                           values="meta_share_pct", fill_value=0)
    pct_change = pivot.pct_change() * 100

    breakouts = []
    for month in pct_change.index[1:]:
        for arch in pct_change.columns:
            change = pct_change.loc[month, arch]
            if change > threshold and pivot.loc[month, arch] > 1.0:
                breakouts.append({
                    "month": month,
                    "archetype": arch,
                    "share_pct": pivot.loc[month, arch],
                    "change_pct": round(change, 1),
                })
    return pd.DataFrame(breakouts)


def get_tier_list(conn: sqlite3.Connection, months: int = 3,
                  source=None, min_size=1, min_date=None, max_date=None) -> pd.DataFrame:
    """Tier list based on meta share. If min_date/max_date are given, uses that
    full range; otherwise falls back to the most recent `months` months."""
    df = get_meta_share(conn, min_date=min_date, max_date=max_date,
                        source=source, min_size=min_size)
    if df.empty:
        return df
    if min_date or max_date:
        recent = df
    else:
        recent_months = sorted(df["month"].unique())[-months:]
        recent = df[df["month"].isin(recent_months)]

    tiers = recent.groupby("archetype").agg(
        avg_share=("meta_share_pct", "mean"),
        total_decks=("deck_count", "sum"),
    ).reset_index().sort_values("avg_share", ascending=False)

    tiers["tier"] = pd.cut(
        tiers["avg_share"],
        bins=[-1, 2, 5, 100],
        labels=["Tier 3", "Tier 2", "Tier 1"],
    )
    return tiers
