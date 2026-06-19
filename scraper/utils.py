import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse


def parse_date(date_str: str) -> str:
    """Parse DD/MM/YYYY to ISO YYYY-MM-DD string."""
    date_str = date_str.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")


def parse_position(position_str: str) -> tuple[int | None, int | None]:
    """Parse '5 of 138' into (position, total_players)."""
    match = re.search(r"(\d+)\s+of\s+(\d+)", position_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def extract_deck_ids(href: str) -> tuple[int | None, int | None]:
    """Extract tournament_id and deck_id from deck.php URL."""
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    tournament_id = int(params["id"][0]) if "id" in params else None
    deck_id = int(params["iddeck"][0]) if "iddeck" in params else None
    return tournament_id, deck_id


def detect_source(tournament_name: str) -> str:
    """Detect tournament source from its name."""
    name_lower = tournament_name.lower()
    if any(kw in name_lower for kw in ("mtgo", "league", "challenge", "preliminary", "showcase")):
        return "mol"
    if "webcam" in name_lower:
        return "webcam"
    return "paper"
