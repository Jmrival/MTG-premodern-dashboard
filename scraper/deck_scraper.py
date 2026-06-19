import re
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from scraper.models import DeckCard

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tcdecks.net"
DECK_URL = f"{BASE_URL}/deck.php"


class DeckScraper:
    """Scrapes card lists from deck.php using requests (no browser needed).

    Key session requirements discovered via reverse engineering:
    - Cookie 'verificado=1' must be set
    - PHPSESSID is obtained by visiting any page first
    - Accept-Encoding header is required (site blocks without it)
    - Sec-Fetch-* headers must be present
    """

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",  # CRITICAL — site blocks without this
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": f"{BASE_URL}/results.php?format=Premodern&src=all&page=1",
        })
        retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retry))

        session.cookies.set("verificado", "1", domain="www.tcdecks.net", path="/")
        # Prime the session to obtain PHPSESSID
        session.get(f"{BASE_URL}/results.php?format=Premodern&src=all&page=1", timeout=30)
        return session

    def reinit_session(self):
        """Recreate session — call when getting consecutive blocks."""
        self.session = self._create_session()

    def scrape_deck(self, deck_id: int, tournament_id: int) -> list[DeckCard] | None:
        """Scrape a single deck. Returns list of DeckCard or None if blocked/empty."""
        url = f"{DECK_URL}?id={tournament_id}&iddeck={deck_id}"
        response = self.session.get(url, timeout=30)
        time.sleep(self.delay)
        return self._parse_deck_html(response.text, deck_id)

    def _parse_deck_html(self, html: str, deck_id: int) -> list[DeckCard] | None:
        if "Acceso Denegado" in html or len(html) < 500:
            return None

        soup = BeautifulSoup(html, "lxml")
        deck_table = soup.find("table", class_="table_deck")
        if not deck_table:
            return None

        # Data layout (confirmed via inspection):
        #   data_cells[0]   = mainboard column left  (creatures, instants, etc.)
        #   data_cells[1]   = mainboard column right  (sorceries, artifacts, lands)
        #   data_cells[2]   = sideboard
        # Each column has <h6>CardType [N]</h6> headers followed by card links.
        # Sideboard column has NO <h6> headers.
        data_cells = deck_table.find_all("td", valign="top")
        if not data_cells:
            return None

        # Determine which cell index is sideboard
        # With 3 cells: last = sideboard. With 2 cells: last = sideboard.
        # With 1 cell: no sideboard.
        sideboard_idx = len(data_cells) - 1 if len(data_cells) >= 2 else None

        # Pattern: N <a href="..." name="CardName" ...>
        card_pattern = re.compile(
            r'(\d+)\s*<a\b[^>]*?href="([^"]+)"[^>]*?name="([^"]+)"[^>]*?>'
        )
        # Card type from h6: "Creatures [4]" → "Creature"
        # Normalize to singular
        TYPE_MAP = {
            "Creatures": "Creature",
            "Instants": "Instant",
            "Sorceries": "Sorcery",
            "Artifacts": "Artifact",
            "Enchantments": "Enchantment",
            "Planeswalkers": "Planeswalker",
            "Land": "Land",
            "Lands": "Land",
            "Battle": "Battle",
        }

        cards = []

        for cell_idx, cell in enumerate(data_cells):
            is_sideboard = (cell_idx == sideboard_idx)
            cell_html = str(cell)

            # Split by <h6> tags to track current card type
            # Format: parts alternate between h6 tags and content sections
            parts = re.split(r'(<h6>[^<]*</h6>)', cell_html)
            current_type = None  # Sideboard cells have no h6, stays None

            for part in parts:
                # Check for h6 type header
                h6_match = re.match(r'<h6>([^[<]+?)(?:\s*\[\d+\])?\s*</h6>', part.strip())
                if h6_match:
                    raw_type = h6_match.group(1).strip()
                    current_type = TYPE_MAP.get(raw_type, raw_type)
                    continue

                # Parse card links in this section
                for m in card_pattern.finditer(part):
                    qty = int(m.group(1))
                    href = m.group(2)
                    card_name = m.group(3).strip()

                    # Extract cardmarket_id from href
                    cm_id_match = re.search(r'idProduct=(\d+)', href)
                    cardmarket_id = int(cm_id_match.group(1)) if cm_id_match else None

                    # Strip UTM tracking params from URL
                    cardmarket_url = re.split(r'&utm_', href)[0] if href else None

                    cards.append(DeckCard(
                        deck_id=deck_id,
                        card_name=card_name,
                        quantity=qty,
                        is_sideboard=is_sideboard,
                        card_type=current_type,       # None for sideboard
                        cardmarket_id=cardmarket_id,
                        cardmarket_url=cardmarket_url,
                    ))

        return cards if cards else None
