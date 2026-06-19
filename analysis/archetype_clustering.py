import pandas as pd
import numpy as np
import sqlite3
from sklearn.feature_extraction.text import TfidfVectorizer


def build_deck_documents(conn: sqlite3.Connection) -> pd.DataFrame:
    """Build 'documents' from decks where each card repeated by quantity."""
    df = pd.read_sql_query(
        """SELECT dc.deck_id, dc.card_name, dc.quantity, d.archetype
           FROM deck_cards dc
           JOIN decks d ON dc.deck_id = d.id
           WHERE dc.is_sideboard = 0""",
        conn,
    )

    docs = df.groupby(["deck_id", "archetype"]).apply(
        lambda g: " ".join(
            [name for name, qty in zip(g["card_name"], g["quantity"])
             for _ in range(qty)]
        )
    ).reset_index()
    docs.columns = ["deck_id", "archetype", "document"]
    return docs


def tfidf_transform(docs: pd.DataFrame, max_features: int = 500):
    """Apply TF-IDF to deck documents."""
    vectorizer = TfidfVectorizer(max_features=max_features, token_pattern=r"[A-Za-z'][A-Za-z' ,]+")
    tfidf_matrix = vectorizer.fit_transform(docs["document"])
    feature_names = vectorizer.get_feature_names_out()
    return tfidf_matrix, feature_names, vectorizer


def reduce_umap(tfidf_matrix, n_components: int = 2, n_neighbors: int = 30,
                min_dist: float = 0.1):
    """UMAP dimensionality reduction."""
    from umap import UMAP
    reducer = UMAP(n_components=n_components, n_neighbors=n_neighbors,
                   min_dist=min_dist, random_state=42)
    embedding = reducer.fit_transform(tfidf_matrix)
    return embedding, reducer


def cluster_hdbscan(embedding, min_cluster_size: int = 20, min_samples: int = 5):
    """HDBSCAN clustering on UMAP embedding."""
    import hdbscan
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size,
                                 min_samples=min_samples)
    labels = clusterer.fit_predict(embedding)
    return labels, clusterer


def full_clustering_pipeline(conn: sqlite3.Connection) -> pd.DataFrame:
    """Run complete clustering: TF-IDF -> UMAP -> HDBSCAN."""
    docs = build_deck_documents(conn)
    if docs.empty:
        return pd.DataFrame()

    tfidf_matrix, features, _ = tfidf_transform(docs)
    embedding, _ = reduce_umap(tfidf_matrix)
    labels, _ = cluster_hdbscan(embedding)

    docs["umap_x"] = embedding[:, 0]
    docs["umap_y"] = embedding[:, 1]
    docs["cluster"] = labels

    return docs[["deck_id", "archetype", "umap_x", "umap_y", "cluster"]]
