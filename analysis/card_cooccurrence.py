import numpy as np
import pandas as pd
import sqlite3
from scipy.sparse import csr_matrix
from collections import defaultdict


def build_card_matrix(conn: sqlite3.Connection,
                      min_decks: int = 10,
                      sideboard: bool = False,
                      include_sideboard: bool | None = None,
                      archetype: str | None = None,
                      card_types: list[str] | None = None,
                      exclude_basic_lands: bool = True) -> tuple[pd.DataFrame, list[str]]:
    """Build binary deck-card presence matrix.

    `include_sideboard` supersedes the legacy `sideboard` param when provided.
    `archetype` restricts to decks of that archetype only.
    `card_types` restricts to cards whose card_type is in the list (None = all types).
    `exclude_basic_lands` drops cards whose type_line starts with 'Basic'.
    """
    if include_sideboard is not None:
        use_side = include_sideboard
    else:
        use_side = sideboard

    side_filter = "" if use_side else "AND dc.is_sideboard = 0"
    arch_filter = ""
    basic_filter = "AND (c.type_line IS NULL OR c.type_line NOT LIKE 'Basic%')" if exclude_basic_lands else ""
    params: list = []
    if archetype:
        arch_filter = "AND d.archetype = ?"
        params.append(archetype)

    type_filter = ""
    if card_types:
        placeholders = ",".join("?" * len(card_types))
        type_filter = f"AND c.card_type IN ({placeholders})"
        params.extend(card_types)

    df = pd.read_sql_query(
        f"""SELECT dc.deck_id, dc.card_name
            FROM deck_cards dc
            JOIN decks d ON d.id = dc.deck_id
            JOIN cards c ON c.name = dc.card_name
            WHERE 1=1 {side_filter} {arch_filter} {basic_filter} {type_filter}""",
        conn,
        params=params,
    )

    card_counts = df["card_name"].value_counts()
    valid_cards = card_counts[card_counts >= min_decks].index.tolist()
    df = df[df["card_name"].isin(valid_cards)]

    matrix = df.pivot_table(index="deck_id", columns="card_name",
                            aggfunc="size", fill_value=0)
    matrix = (matrix > 0).astype(int)

    return matrix, valid_cards


def compute_raw_cooccurrence(matrix: pd.DataFrame) -> pd.DataFrame:
    """Count how many decks each pair of cards shares (raw co-occurrence).

    Returns a symmetric DataFrame of the same shape as the PMI matrix —
    intercambiable with compute_pmi() output in get_top_pairs().
    """
    arr = matrix.values
    raw = arr.T @ arr
    np.fill_diagonal(raw, 0)
    return pd.DataFrame(raw, index=matrix.columns, columns=matrix.columns)


def compute_pmi(matrix: pd.DataFrame, top_n: int = 500) -> pd.DataFrame:
    """Compute Pointwise Mutual Information for card pairs."""
    n_decks = len(matrix)
    card_probs = matrix.sum() / n_decks

    top_cards = card_probs.nlargest(top_n).index.tolist()
    m = matrix[top_cards].values

    co_occur = m.T @ m
    np.fill_diagonal(co_occur, 0)
    co_occur_prob = co_occur / n_decks

    probs = card_probs[top_cards].values
    expected = np.outer(probs, probs)

    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log2(co_occur_prob / expected)
        pmi[~np.isfinite(pmi)] = 0

    pmi_df = pd.DataFrame(pmi, index=top_cards, columns=top_cards)
    return pmi_df


def get_top_pairs(pmi_df: pd.DataFrame, n: int = 50) -> pd.DataFrame:
    """Get top N card pairs by PMI."""
    pairs = []
    seen = set()
    for card_a in pmi_df.index:
        for card_b in pmi_df.columns:
            if card_a >= card_b:
                continue
            key = (card_a, card_b)
            if key not in seen:
                seen.add(key)
                pairs.append({
                    "card_a": card_a,
                    "card_b": card_b,
                    "pmi": pmi_df.loc[card_a, card_b],
                })

    return pd.DataFrame(pairs).nlargest(n, "pmi")


def build_cooccurrence_graph(pmi_df: pd.DataFrame, threshold: float = 1.0):
    """Build NetworkX graph from PMI matrix."""
    import networkx as nx

    G = nx.Graph()
    for card_a in pmi_df.index:
        for card_b in pmi_df.columns:
            if card_a >= card_b:
                continue
            pmi_val = pmi_df.loc[card_a, card_b]
            if pmi_val > threshold:
                G.add_edge(card_a, card_b, weight=pmi_val)

    return G
