"""Actualización incremental de la base de datos MTG Premodern.

Hace exactamente lo mismo que el notebook 03 pero desde consola, sin Colab.

Pasos:
  1. Scrapea páginas nuevas de tcdecks.net (solo torneos/mazos no existentes)
  2. Scrapea cartas de mazos pendientes (cards_scraped = 0)
  3. Sincroniza metadata de cartas nuevas con Scryfall
  4. Refresca precios de todas las cartas

Uso:
    python db/update.py [ruta/a/premodern.db] [--metadata-only] [--prices-only]
                        [--no-scrape] [--no-scryfall]

Opciones:
    --no-scrape      Saltea el scraping de tcdecks.net (solo Scryfall)
    --no-scryfall    Saltea la sincronización con Scryfall (solo scraping)
    --metadata-only  Solo sincroniza metadata nueva (sin refrescar precios)
    --prices-only    Solo refresca precios (sin metadata nueva)
"""

import logging
import sqlite3
import sys
import time
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.db_writer import DBWriter
from scraper.deck_scraper import DeckScraper
from scraper.results_scraper import ResultsScraper
from db.sync_scryfall import ensure_schema, refresh_prices, sync_metadata

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
)

STOP_AFTER_KNOWN_PAGES = 3  # Parar tras N páginas consecutivas sin mazos nuevos


def scrape_incremental(db_path: str) -> None:
    """Scrapea solo torneos y mazos que no existen en la DB."""
    writer = DBWriter(db_path)
    scraper = ResultsScraper(delay=1.5)

    existing_ids = set(
        r[0] for r in writer.conn.execute("SELECT id FROM decks").fetchall()
    )
    print(f"[scraping] Mazos existentes en DB: {len(existing_ids):,}")

    total_pages = scraper.get_total_pages()
    new_decks = 0
    consecutive_known = 0
    page = 1

    with tqdm(total=total_pages, desc="Páginas scrapeadas", unit="pág") as pbar:
        while page <= total_pages:
            try:
                results = scraper.scrape_page(page)
            except Exception as e:
                print(f"  [warn] Error en página {page}: {e}")
                page += 1
                pbar.update(1)
                continue

            page_new = 0
            for tournament, deck in results:
                writer.upsert_tournament(tournament)
                if deck.id not in existing_ids:
                    inserted = writer.insert_deck(deck)
                    if inserted:
                        existing_ids.add(deck.id)
                        page_new += 1
                        new_decks += 1

            writer.commit()

            if page_new == 0:
                consecutive_known += 1
                if consecutive_known >= STOP_AFTER_KNOWN_PAGES:
                    pbar.update(total_pages - page)
                    print(f"\n[scraping] {STOP_AFTER_KNOWN_PAGES} páginas consecutivas sin novedades — deteniendo.")
                    break
            else:
                consecutive_known = 0

            page += 1
            pbar.update(1)

    writer.close()
    print(f"[scraping] Torneos/mazos nuevos agregados: {new_decks:,}")


def scrape_cards(db_path: str) -> None:
    """Scrapea cartas de mazos que aún no tienen cards_scraped = 1."""
    writer = DBWriter(db_path)
    pending = writer.get_unscraped_decks()
    print(f"[cartas] Mazos pendientes de scrapear: {len(pending):,}")

    if not pending:
        print("[cartas] Nada que scrapear.")
        writer.close()
        return

    scraper = DeckScraper(delay=0.5)
    errors = 0
    consecutive_errors = 0

    for deck_id, tournament_id in tqdm(pending, desc="Mazos", unit="mazo"):
        try:
            cards = scraper.scrape_deck(deck_id, tournament_id)
            if cards:
                writer.insert_deck_cards(cards, deck_id)
                writer.commit()
                consecutive_errors = 0
            else:
                # Dejar cards_scraped = 0 para reintentar en el próximo update
                # (puede ser que el decklist todavía no esté publicado en el sitio)
                errors += 1
                consecutive_errors += 1
        except Exception as e:
            logging.warning(f"Error en mazo {deck_id}: {e}")
            errors += 1
            consecutive_errors += 1

        if consecutive_errors >= 10:
            print("\n[cartas] 10 errores consecutivos — reiniciando sesión...")
            scraper.reinit_session()
            consecutive_errors = 0

    writer.close()
    print(f"[cartas] Completado. Errores/vacíos: {errors:,}")


def run_scryfall(db_path: str, metadata_only: bool, prices_only: bool) -> None:
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    if not prices_only:
        sync_metadata(conn)
    if not metadata_only:
        refresh_prices(conn)
    conn.close()


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

    no_scrape = "--no-scrape" in flags
    no_scryfall = "--no-scryfall" in flags
    metadata_only = "--metadata-only" in flags
    prices_only = "--prices-only" in flags

    t0 = time.time()

    if not no_scrape:
        print("\n=== Paso 1: Scraping de torneos y mazos nuevos ===")
        scrape_incremental(db_path)

        print("\n=== Paso 2: Scraping de cartas pendientes ===")
        scrape_cards(db_path)

    if not no_scryfall:
        print("\n=== Paso 3: Sincronización con Scryfall ===")
        run_scryfall(db_path, metadata_only=metadata_only, prices_only=prices_only)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    print(f"\nListo. Tiempo total: {mins}m {secs}s")


if __name__ == "__main__":
    main()
