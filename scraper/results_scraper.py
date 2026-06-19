import logging
import re
from bs4 import BeautifulSoup
from scraper.base import BaseScraper
from scraper.models import Tournament, Deck
from scraper.utils import parse_date, parse_position, extract_deck_ids, detect_source

logger = logging.getLogger(__name__)

RESULTS_URL = "https://www.tcdecks.net/results.php"

# Estructura HTML real de tcdecks.net/results.php:
#   <tr>  (sin clase, plain tr)
#     <td data-th="Archetype">       <a href="deck.php?id=T&iddeck=D">Archetype</a>
#     <td data-th="Format">          <a href="...">Premodern</a>
#     <td data-th="Player">          <a href="...">PlayerName</a>
#     <td data-th="Tournament Name"> <a href="deck.php?id=T">Tournament - Date</a>
#     <td data-th="Position">        X of Y
#     <td data-th="Date">            DD/MM/YYYY


class ResultsScraper(BaseScraper):
    def scrape_page(self, page: int) -> list[tuple[Tournament, Deck]]:
        """Scrape a single page of results.php. Returns list of (Tournament, Deck) pairs."""
        response = self.get(RESULTS_URL, params={
            "format": "Premodern",
            "src": "all",
            "page": page,
        })
        return self._parse_page(response.text)

    def _parse_page(self, html: str) -> list[tuple[Tournament, Deck]]:
        soup = BeautifulSoup(html, "lxml")
        results = []

        for row in soup.find_all("tr"):
            try:
                result = self._parse_row(row)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to parse row: {e}")
                continue

        return results

    def _parse_row(self, row) -> tuple[Tournament, Deck] | None:
        cells = row.find_all("td")
        if len(cells) < 6:
            return None

        # Verify it's a data row (has data-th attribute)
        if not cells[0].get("data-th"):
            return None

        # Cell 0: Archetype + link with iddeck
        arch_link = cells[0].find("a", href=True)
        if not arch_link:
            return None
        archetype = arch_link.get_text(strip=True)
        href = arch_link.get("href", "")

        tournament_id, deck_id = extract_deck_ids(href)
        if not tournament_id or not deck_id:
            return None

        # Cell 2: Player
        player_link = cells[2].find("a")
        player_name = player_link.get_text(strip=True) if player_link else "Unknown"

        # Cell 3: Tournament Name
        tourn_link = cells[3].find("a")
        tournament_name = tourn_link.get_text(strip=True) if tourn_link else "Unknown"

        # Cell 4: Position ("X of Y")
        position_text = cells[4].get_text(strip=True)
        position, total_players = parse_position(position_text)

        # Cell 5: Date (DD/MM/YYYY)
        date_text = cells[5].get_text(strip=True)
        if not date_text:
            return None
        parsed_date = parse_date(date_text)

        source = detect_source(tournament_name)

        # Build URLs
        tournament_url = f"https://www.tcdecks.net/deck.php?id={tournament_id}"
        archetype_url = f"https://www.tcdecks.net/archetype.php?archetype={archetype}&format=Premodern"

        tournament = Tournament(
            id=tournament_id,
            name=tournament_name,
            date=parsed_date,
            player_count=total_players,
            source=source,
            url=tournament_url,
        )

        deck = Deck(
            id=deck_id,
            tournament_id=tournament_id,
            player_name=player_name,
            archetype=archetype,
            archetype_url=archetype_url,
            date=parsed_date,
            position=position,
            total_players=total_players,
        )

        return tournament, deck

    def get_total_pages(self) -> int:
        """Get the total number of pages from the first page."""
        response = self.get(RESULTS_URL, params={
            "format": "Premodern",
            "src": "all",
            "page": 1,
        })
        soup = BeautifulSoup(response.text, "lxml")
        max_page = 1
        for link in soup.select("a[href*='page=']"):
            href = link.get("href", "")
            match = re.search(r"page=(\d+)", href)
            if match:
                max_page = max(max_page, int(match.group(1)))
        return max_page
