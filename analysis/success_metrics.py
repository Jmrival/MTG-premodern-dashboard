import math
import pandas as pd
import sqlite3


def performance_score(position: int, total_players: int) -> float:
    """Normalized performance score weighted by tournament size."""
    if total_players <= 1:
        return 0.0
    percentile = 1 - (position - 1) / (total_players - 1)
    size_weight = math.log2(max(total_players, 2))
    return percentile * size_weight


def get_archetype_success(conn: sqlite3.Connection,
                          min_entries: int = 10,
                          min_tournament_size: int = 8,
                          min_date=None, max_date=None,
                          source=None, country=None, archetypes=None) -> pd.DataFrame:
    """Success metrics per archetype."""
    conditions = ["total_players >= ?", "position IS NOT NULL"]
    params = [min_tournament_size]

    if min_date:
        conditions.append("date >= ?")
        params.append(min_date)
    if max_date:
        conditions.append("date <= ?")
        params.append(max_date)
    if source and source != "all":
        conditions.append(
            "tournament_id IN (SELECT id FROM tournaments WHERE source = ?)"
        )
        params.append(source)
    if country and country != "all":
        conditions.append(
            "tournament_id IN (SELECT id FROM tournaments WHERE country = ?)"
        )
        params.append(country)
    if archetypes:
        placeholders = ",".join(["?"] * len(archetypes))
        conditions.append(f"archetype IN ({placeholders})")
        params.extend(archetypes)

    where = " AND ".join(conditions)
    df = pd.read_sql_query(
        f"SELECT archetype, position, total_players FROM decks WHERE {where}",
        conn, params=params,
    )

    if df.empty:
        return df

    df["perf_score"] = df.apply(
        lambda r: performance_score(r["position"], r["total_players"]), axis=1
    )
    df["is_top8"] = df["position"] <= 8
    df["is_top4"] = df["position"] <= 4
    df["is_winner"] = df["position"] == 1
    df["relative_pos"] = df["position"] / df["total_players"]

    agg = df.groupby("archetype").agg(
        total_entries=("position", "count"),
        avg_perf_score=("perf_score", "mean"),
        top8_rate=("is_top8", "mean"),
        top4_rate=("is_top4", "mean"),
        win_rate=("is_winner", "mean"),
        avg_relative_pos=("relative_pos", "mean"),
        consistency=("perf_score", "std"),
    ).reset_index()

    agg = agg[agg["total_entries"] >= min_entries]
    return agg.round(4).sort_values("avg_perf_score", ascending=False)


def get_archetype_success_over_time(conn: sqlite3.Connection,
                                    archetype: str = None,
                                    min_date=None, max_date=None,
                                    source=None, min_size=None, country=None) -> pd.DataFrame:
    """Monthly success metrics, optionally filtered by archetype."""
    effective_min_size = max(8, min_size) if min_size else 8
    conditions = [f"total_players >= {effective_min_size}", "position IS NOT NULL"]
    params = []

    if archetype:
        conditions.append("archetype = ?")
        params.append(archetype)
    if min_date:
        conditions.append("date >= ?")
        params.append(min_date)
    if max_date:
        conditions.append("date <= ?")
        params.append(max_date)
    if source and source != "all":
        conditions.append(
            "tournament_id IN (SELECT id FROM tournaments WHERE source = ?)"
        )
        params.append(source)
    if country and country != "all":
        conditions.append(
            "tournament_id IN (SELECT id FROM tournaments WHERE country = ?)"
        )
        params.append(country)

    where = " AND ".join(conditions)
    df = pd.read_sql_query(
        f"""SELECT archetype, strftime('%Y-%m', date) as month,
                   position, total_players
            FROM decks WHERE {where}""",
        conn, params=params,
    )
    if df.empty:
        return df

    df["perf_score"] = df.apply(
        lambda r: performance_score(r["position"], r["total_players"]), axis=1
    )
    df["is_top8"] = df["position"] <= 8

    agg = df.groupby(["archetype", "month"]).agg(
        entries=("position", "count"),
        avg_perf_score=("perf_score", "mean"),
        top8_rate=("is_top8", "mean"),
    ).reset_index()

    return agg.sort_values(["archetype", "month"])
