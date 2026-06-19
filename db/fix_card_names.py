"""Fix typos and mismatched card names in the database.

Workflow:
1. Run --list to see all cards not yet synced with Scryfall (scryfall_id IS NULL).
2. Edit the CORRECTIONS dict below with any typos you want to fix.
3. Run --apply (dry-run first with --dry-run) to rename them in the DB.
4. Re-run db/sync_scryfall.py to fetch the metadata for the fixed names.

Usage:
    python db/fix_card_names.py [path/to/premodern.db] --list
    python db/fix_card_names.py [path/to/premodern.db] --apply --dry-run
    python db/fix_card_names.py [path/to/premodern.db] --apply
"""

import sqlite3
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# CORRECTIONS DICTIONARY
# Key   = name as it appears in the DB (wrong / unrecognized)
# Value = correct Scryfall name
#
# Split cards use " // " (space-slash-slash-space) — that IS the Scryfall format,
# so if they appear here it means the DB has a different separator. Check with
# --list and compare against https://scryfall.com/search?q=name%3A%22fire+%2F%2F+ice%22
# ──────────────────────────────────────────────────────────────────────────────
CORRECTIONS: dict[str, str] = {
    # Confirmed typos from the scraper
    "Mox Dismond": "Mox Diamond",

    # Add more below as you discover them via --list:
    # "Swords to Plowshare": "Swords to Plowshares",
    # "Lightning Bolts": "Lightning Bolt",
}

# Cards to DELETE entirely (tokens, art cards, misidentified entries, etc.)
# These will be removed from deck_cards and cards tables.
DELETE_ENTRIES: list[str] = [
    "Art Series: Valley of Gorgoroth",
    # Add other non-card entries here
]


# ──────────────────────────────────────────────────────────────────────────────
# Core functions
# ──────────────────────────────────────────────────────────────────────────────

def list_unsynced(conn: sqlite3.Connection) -> None:
    """Print all cards with scryfall_id IS NULL, sorted by usage frequency."""
    rows = conn.execute(
        """SELECT c.name,
                  COALESCE(u.deck_count, 0) AS deck_count,
                  c.card_type
           FROM cards c
           LEFT JOIN (
               SELECT card_name, COUNT(DISTINCT deck_id) AS deck_count
               FROM deck_cards GROUP BY card_name
           ) u ON u.card_name = c.name
           WHERE c.scryfall_id IS NULL
           ORDER BY deck_count DESC, c.name"""
    ).fetchall()

    if not rows:
        print("✓ Todas las cartas están sincronizadas con Scryfall.")
        return

    print(f"\n{'Carta':<50} {'Mazos':>6}  {'Tipo'}")
    print("─" * 72)
    for name, deck_count, card_type in rows:
        print(f"{name:<50} {deck_count:>6}  {card_type or '—'}")
    print(f"\nTotal: {len(rows)} cartas sin sincronizar")
    print("\nPara corregir typos: editá el diccionario CORRECTIONS en db/fix_card_names.py")
    print("Para borrar entradas inválidas: editá DELETE_ENTRIES en db/fix_card_names.py")


def _rename_card(conn: sqlite3.Connection, old_name: str, new_name: str, dry_run: bool) -> bool:
    """Rename a card across all tables. Returns True if successful."""
    # Check old name exists
    exists = conn.execute("SELECT 1 FROM cards WHERE name = ?", (old_name,)).fetchone()
    if not exists:
        print(f"  SKIP  '{old_name}' — no existe en la DB")
        return False

    # Check new name doesn't already exist
    target_exists = conn.execute("SELECT 1 FROM cards WHERE name = ?", (new_name,)).fetchone()
    if target_exists:
        # Merge: reassign deck_cards to the existing target, then delete old
        deck_count = conn.execute(
            "SELECT COUNT(*) FROM deck_cards WHERE card_name = ?", (old_name,)
        ).fetchone()[0]
        print(f"  MERGE '{old_name}' → '{new_name}' (ya existe, fusionando {deck_count} registros)")
        if not dry_run:
            # deck_cards PK is (deck_id, card_name, is_sideboard) — use INSERT OR REPLACE
            conn.execute(
                """INSERT OR REPLACE INTO deck_cards (deck_id, card_name, quantity, is_sideboard)
                   SELECT deck_id, ?, quantity, is_sideboard FROM deck_cards WHERE card_name = ?""",
                (new_name, old_name),
            )
            conn.execute("DELETE FROM deck_cards WHERE card_name = ?", (old_name,))
            conn.execute("DELETE FROM card_price_history WHERE card_name = ?", (old_name,))
            conn.execute("DELETE FROM cards WHERE name = ?", (old_name,))
        return True

    deck_count = conn.execute(
        "SELECT COUNT(*) FROM deck_cards WHERE card_name = ?", (old_name,)
    ).fetchone()[0]
    print(f"  RENAME '{old_name}' → '{new_name}' ({deck_count} registros en deck_cards)")
    if not dry_run:
        # Temporarily disable FK enforcement to rename the PK safely
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("UPDATE cards SET name = ? WHERE name = ?", (new_name, old_name))
        conn.execute("UPDATE deck_cards SET card_name = ? WHERE card_name = ?", (new_name, old_name))
        conn.execute(
            "UPDATE card_price_history SET card_name = ? WHERE card_name = ?", (new_name, old_name)
        )
        conn.execute("PRAGMA foreign_keys = ON")
    return True


def _delete_card(conn: sqlite3.Connection, name: str, dry_run: bool) -> None:
    """Remove a card and all its deck_cards entries."""
    exists = conn.execute("SELECT 1 FROM cards WHERE name = ?", (name,)).fetchone()
    if not exists:
        print(f"  SKIP  '{name}' — no existe en la DB")
        return
    deck_count = conn.execute(
        "SELECT COUNT(*) FROM deck_cards WHERE card_name = ?", (name,)
    ).fetchone()[0]
    print(f"  DELETE '{name}' ({deck_count} registros en deck_cards)")
    if not dry_run:
        conn.execute("DELETE FROM deck_cards WHERE card_name = ?", (name,))
        conn.execute("DELETE FROM card_price_history WHERE card_name = ?", (name,))
        conn.execute("DELETE FROM cards WHERE name = ?", (name,))


def apply_corrections(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    """Apply CORRECTIONS renames and DELETE_ENTRIES removals."""
    if dry_run:
        print("[DRY RUN — no se modificará la DB]\n")

    if CORRECTIONS:
        print(f"── Correcciones ({len(CORRECTIONS)}) ──")
        for old, new in CORRECTIONS.items():
            _rename_card(conn, old, new, dry_run)

    if DELETE_ENTRIES:
        print(f"\n── Eliminaciones ({len(DELETE_ENTRIES)}) ──")
        for name in DELETE_ENTRIES:
            _delete_card(conn, name, dry_run)

    if not dry_run:
        conn.commit()
        print("\n✓ Cambios aplicados. Ahora corré sync_scryfall.py para sincronizar las cartas renombradas.")
    else:
        print("\nPasá --apply sin --dry-run para ejecutar los cambios.")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    positional = [a for a in args if not a.startswith("--")]

    db_path = positional[0] if positional else str(
        Path(__file__).resolve().parent / "premodern.db"
    )
    if not Path(db_path).exists():
        print(f"ERROR: no existe {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)

    if "--list" in flags:
        list_unsynced(conn)
    elif "--apply" in flags:
        apply_corrections(conn, dry_run="--dry-run" in flags)
    else:
        print(__doc__)

    conn.close()


if __name__ == "__main__":
    main()
