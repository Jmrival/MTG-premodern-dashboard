"""Sync card data from the Scryfall API into the local DB.

Two independent operations, both safe to re-run:

1. Metadata sync — for cards never synced before (`scryfall_id IS NULL`), fetches the
   full card object from Scryfall and populates mana cost, type line, oracle text,
   colors, rarity, set info, image, etc. Only needs to run once per card (it won't
   re-fetch cards that already have `scryfall_id` set).

2. Price refresh — re-fetches the cheapest known USD price for every already-synced
   card and appends a row to `card_price_history`, so price trends can be tracked over
   time. Meant to be run periodically (prices change; metadata mostly doesn't).

Usage:
    python db/sync_scryfall.py [path/to/premodern.db] [--metadata-only | --prices-only]

By default runs both steps (metadata sync first, then a price refresh for everything,
including cards that were just synced).
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests

SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
BATCH_SIZE = 75
DELAY = 0.15  # ~6 req/s — comfortably under Scryfall's 10 req/s limit

NEW_COLUMNS = [
    ("mana_cost", "TEXT"),
    ("cmc", "REAL"),
    ("type_line", "TEXT"),
    ("oracle_text", "TEXT"),
    ("flavor_text", "TEXT"),
    ("power", "TEXT"),
    ("toughness", "TEXT"),
    ("loyalty", "TEXT"),
    ("colors", "TEXT"),
    ("color_identity", "TEXT"),
    ("keywords", "TEXT"),
    ("produced_mana", "TEXT"),
    ("rarity", "TEXT"),
    ("set_code", "TEXT"),
    ("set_name", "TEXT"),
    ("released_at", "TEXT"),
    ("collector_number", "TEXT"),
    ("layout", "TEXT"),
    ("image_uri", "TEXT"),
    ("scryfall_id", "TEXT"),
    ("price_usd", "REAL"),
    ("price_updated_at", "TIMESTAMP"),
    ("scryfall_raw", "TEXT"),
    ("scryfall_synced_at", "TIMESTAMP"),
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(cards)").fetchall()}
    for col, typedef in NEW_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE cards ADD COLUMN {col} {typedef}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS card_price_history (
            card_name TEXT NOT NULL REFERENCES cards(name),
            price_usd REAL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (card_name, fetched_at)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_card ON card_price_history(card_name)")
    conn.commit()


def cheapest_usd_price(prices: dict) -> float | None:
    """Pick the lowest available USD price (normal / foil / etched). Ignores EUR and TIX."""
    candidates = [prices.get("usd"), prices.get("usd_foil"), prices.get("usd_etched")]
    nums = [float(p) for p in candidates if p is not None]
    return min(nums) if nums else None


def cheapest_usd_across_prints(card_name: str) -> float | None:
    """Search all printings of a card and return the lowest available USD price.

    Uses /cards/search?unique=prints to scan every edition and takes the global
    minimum across normal/foil/etched prices. This is the canonical price source —
    the batch /cards/collection endpoint only returns one printing and may miss
    cheaper editions (e.g. Mox Diamond's default print has no USD price).

    Handles 429 rate-limit responses with exponential backoff (up to 3 retries).
    """
    url = "https://api.scryfall.com/cards/search"
    params = {"q": f'!"{card_name}"', "unique": "prints"}
    for attempt in range(4):
        try:
            resp = _session.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                prices = []
                for card in resp.json().get("data", []):
                    p = cheapest_usd_price(card.get("prices", {}) or {})
                    if p is not None:
                        prices.append(p)
                return min(prices) if prices else None
            if resp.status_code == 404:
                return None  # card genuinely not found
            if resp.status_code == 429:
                wait = 2 ** attempt  # 1, 2, 4, 8 s
                print(f"  [rate limit] esperando {wait}s antes de reintentar '{card_name}' …")
                time.sleep(wait)
                continue
            print(f"  [Scryfall] HTTP {resp.status_code} para '{card_name}': {resp.text[:100]}")
            return None
        except Exception as e:
            print(f"  [Scryfall] error en '{card_name}': {e}")
            return None
    return None


def _join_list(values) -> str:
    return ",".join(values) if values else ""


_session = requests.Session()
_session.headers.update({
    "User-Agent": "MTGPremodernAnalytics/1.0 (github.com/Jmrival/MTG-premodern-dashboard)",
    "Accept": "application/json",
})


def _post_collection(identifiers: list[dict]) -> tuple[list, list]:
    """POST to /cards/collection. Returns (found_cards, not_found_identifiers)."""
    resp = _session.post(
        SCRYFALL_COLLECTION_URL, json={"identifiers": identifiers}, timeout=30
    )
    if resp.status_code == 400:
        print(f"[Scryfall] Batch rechazado (400): {resp.text[:200]}")
        return [], identifiers
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", []), data.get("not_found", [])


def fetch_scryfall_batch(card_names: list[str]) -> tuple[dict, list[str]]:
    """Query Scryfall in batches of 75 names. Returns (name -> raw card dict, not_found).

    Split cards (e.g. "Fire // Ice") are retried using only the first face name,
    since Scryfall's collection endpoint doesn't match on the full combined name.
    Results are stored under the original DB name so no renames are needed.
    """
    results = {}
    not_found = []

    for i in range(0, len(card_names), BATCH_SIZE):
        batch = card_names[i:i + BATCH_SIZE]
        identifiers = [{"name": n} for n in batch if n and str(n).strip()]
        if not identifiers:
            continue

        found_cards, nf_raw = _post_collection(identifiers)

        for card in found_cards:
            results[card["name"]] = card

        # Retry split cards not found in this batch using first-face name only.
        # Store result under the original "First // Second" name so the DB stays consistent.
        split_retry: dict[str, str] = {}  # first_face -> original_name
        for nf_item in nf_raw:
            orig = nf_item.get("name", "")
            if " // " in orig:
                first_face = orig.split(" // ")[0].strip()
                split_retry[first_face] = orig
            else:
                not_found.append(orig)

        if split_retry:
            retry_ids = [{"name": fn} for fn in split_retry]
            retry_found, retry_nf = _post_collection(retry_ids)
            for card in retry_found:
                # Map back to the original combined name
                orig_name = split_retry.get(card["name"], card["name"])
                results[orig_name] = card
            for nf_item in retry_nf:
                orig = split_retry.get(nf_item.get("name", ""), nf_item.get("name", ""))
                not_found.append(orig)

        time.sleep(DELAY)

    return results, not_found


def sync_metadata(conn: sqlite3.Connection) -> None:
    """Fetch and store full card metadata for cards never synced before."""
    pending = [
        r[0] for r in conn.execute(
            "SELECT name FROM cards WHERE scryfall_id IS NULL"
        ).fetchall()
    ]
    print(f"[metadata] Cartas pendientes de sincronizar: {len(pending):,}")
    if not pending:
        print("[metadata] Nada que actualizar.")
        return

    results, not_found = fetch_scryfall_batch(pending)

    for name, card in results.items():
        mana_cost = card.get("mana_cost", "") or ""
        if not mana_cost and "card_faces" in card:
            faces = card["card_faces"]
            mana_cost = "//".join(f.get("mana_cost", "") or "" for f in faces)

        price = cheapest_usd_across_prints(name)
        time.sleep(DELAY)

        conn.execute(
            """UPDATE cards SET
                 mana_cost = ?, cmc = ?, type_line = ?, oracle_text = ?, flavor_text = ?,
                 power = ?, toughness = ?, loyalty = ?, colors = ?, color_identity = ?,
                 keywords = ?, produced_mana = ?, rarity = ?, set_code = ?, set_name = ?,
                 released_at = ?, collector_number = ?, layout = ?, image_uri = ?,
                 scryfall_id = ?, price_usd = ?, price_updated_at = CURRENT_TIMESTAMP,
                 scryfall_raw = ?, scryfall_synced_at = CURRENT_TIMESTAMP
               WHERE name = ?""",
            (
                mana_cost,
                card.get("cmc"),
                card.get("type_line"),
                card.get("oracle_text"),
                card.get("flavor_text"),
                card.get("power"),
                card.get("toughness"),
                card.get("loyalty"),
                _join_list(card.get("colors")),
                _join_list(card.get("color_identity")),
                _join_list(card.get("keywords")),
                _join_list(card.get("produced_mana")),
                card.get("rarity"),
                card.get("set"),
                card.get("set_name"),
                card.get("released_at"),
                card.get("collector_number"),
                card.get("layout"),
                (card.get("image_uris") or {}).get("normal"),
                card.get("id"),
                price,
                json.dumps(card),
                name,
            ),
        )
        if price is not None:
            conn.execute(
                "INSERT OR REPLACE INTO card_price_history (card_name, price_usd, fetched_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (name, price),
            )
    conn.commit()

    print(f"[metadata] Actualizadas: {len(results):,}")
    print(f"[metadata] No encontradas en Scryfall: {len(not_found)}")
    if not_found:
        print("[metadata] Ejemplos no encontrados:", not_found[:20])


def refresh_prices(conn: sqlite3.Connection) -> None:
    """Re-fetch the cheapest USD price for every synced card across ALL printings.

    Uses /cards/search?unique=prints per card to guarantee the global minimum price,
    regardless of which edition Scryfall returns as the default. One request per card
    (~2700 cards ≈ 5 min at 0.1 s/req). Appends a row to card_price_history each run.
    """
    synced = [
        r[0] for r in conn.execute(
            "SELECT name FROM cards WHERE scryfall_id IS NOT NULL ORDER BY name"
        ).fetchall()
    ]
    print(f"[prices] Cartas a refrescar: {len(synced):,}")
    if not synced:
        print("[prices] Nada que refrescar (corré la sincronización de metadata primero).")
        return

    updated = 0
    no_price = []
    for i, name in enumerate(synced, 1):
        price = cheapest_usd_across_prints(name)
        time.sleep(DELAY)
        if price is None:
            no_price.append(name)
            continue
        conn.execute(
            "UPDATE cards SET price_usd = ?, price_updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            (price, name),
        )
        conn.execute(
            "INSERT OR REPLACE INTO card_price_history (card_name, price_usd, fetched_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            (name, price),
        )
        updated += 1
        if i % 100 == 0:
            conn.commit()
            print(f"  {i:,}/{len(synced):,} procesadas …")
    conn.commit()

    print(f"[prices] Actualizadas: {updated:,} | Sin precio USD: {len(no_price)}")
    if no_price:
        print("  Sin precio:", no_price[:20])


def main(db_path: str, metadata_only: bool, prices_only: bool) -> None:
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)

    if not prices_only:
        sync_metadata(conn)
    if not metadata_only:
        refresh_prices(conn)

    conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    positional = [a for a in args if not a.startswith("--")]

    db_path = positional[0] if positional else str(
        Path(__file__).resolve().parent / "premodern.db"
    )
    if not Path(db_path).exists():
        print(f"ERROR: no existe {db_path}")
        sys.exit(1)

    main(
        db_path,
        metadata_only="--metadata-only" in flags,
        prices_only="--prices-only" in flags,
    )
