import sqlite3
import logging
from pathlib import Path
from scraper.models import Tournament, Deck, DeckCard

logger = logging.getLogger(__name__)


class DBWriter:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def init_schema(self, schema_path: str | Path):
        with open(schema_path) as f:
            self.conn.executescript(f.read())

    def upsert_tournament(self, t: Tournament):
        self.conn.execute(
            """INSERT INTO tournaments (id, name, date, player_count, source, url)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 player_count = MAX(tournaments.player_count, excluded.player_count),
                 source = CASE WHEN tournaments.source = 'unknown'
                               THEN excluded.source ELSE tournaments.source END,
                 url = COALESCE(tournaments.url, excluded.url)""",
            (t.id, t.name, str(t.date), t.player_count, t.source, t.url),
        )

    def insert_deck(self, d: Deck) -> bool:
        """Insert deck if not exists. Returns True if inserted."""
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO decks
                   (id, tournament_id, player_name, archetype, archetype_url, position, total_players, date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (d.id, d.tournament_id, d.player_name, d.archetype,
                 d.archetype_url, d.position, d.total_players, str(d.date)),
            )
            return self.conn.execute("SELECT changes()").fetchone()[0] > 0
        except sqlite3.IntegrityError:
            logger.warning(f"Deck {d.id} failed FK constraint (tournament {d.tournament_id})")
            return False

    def insert_deck_cards(self, cards: list[DeckCard], deck_id: int):
        for c in cards:
            # Upsert card metadata: only fill in type/cardmarket fields if not already set.
            # This preserves type from mainboard entries (which have h6 headers)
            # when the same card is later seen in a sideboard (no h6 headers → type=None).
            self.conn.execute(
                """INSERT INTO cards (name, card_type, cardmarket_id, cardmarket_url)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     card_type      = COALESCE(cards.card_type,      excluded.card_type),
                     cardmarket_id  = COALESCE(cards.cardmarket_id,  excluded.cardmarket_id),
                     cardmarket_url = COALESCE(cards.cardmarket_url, excluded.cardmarket_url)""",
                (c.card_name, c.card_type, c.cardmarket_id, c.cardmarket_url),
            )
            # Insert deck-card link.
            # PK is (deck_id, card_name, is_sideboard) so the same card in both
            # mainboard and sideboard produces two separate rows.
            self.conn.execute(
                """INSERT OR REPLACE INTO deck_cards
                   (deck_id, card_name, quantity, is_sideboard)
                   VALUES (?, ?, ?, ?)""",
                (c.deck_id, c.card_name, c.quantity, int(c.is_sideboard)),
            )
        self.conn.execute(
            "UPDATE decks SET cards_scraped = 1 WHERE id = ?", (deck_id,)
        )

    def deck_exists(self, deck_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        return row is not None

    def get_unscraped_decks(self, limit: int = None) -> list[tuple[int, int]]:
        """Returns list of (deck_id, tournament_id) for decks without cards."""
        query = "SELECT id, tournament_id FROM decks WHERE cards_scraped = 0"
        if limit:
            query += f" LIMIT {limit}"
        return self.conn.execute(query).fetchall()

    def get_max_date(self) -> str | None:
        row = self.conn.execute("SELECT MAX(date) FROM tournaments").fetchone()
        return row[0] if row else None

    def get_deck_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM decks").fetchone()[0]

    def get_tournament_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM tournaments").fetchone()[0]

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()
