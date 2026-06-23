from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Tournament:
    id: int
    name: str
    date: date
    player_count: Optional[int] = None
    source: str = "unknown"
    format: str = "premodern"
    url: Optional[str] = None


@dataclass
class Deck:
    id: int
    tournament_id: int
    player_name: str
    archetype: str
    date: date
    archetype_url: Optional[str] = None
    position: Optional[int] = None
    total_players: Optional[int] = None
    cards_scraped: bool = False


@dataclass
class Card:
    name: str
    card_type: Optional[str] = None
    cardmarket_id: Optional[int] = None
    cardmarket_url: Optional[str] = None


@dataclass
class DeckCard:
    deck_id: int
    card_name: str
    quantity: int
    is_sideboard: bool = False
    # Card metadata — populated during scraping, stored in cards table
    card_type: Optional[str] = None
    cardmarket_id: Optional[int] = None
    cardmarket_url: Optional[str] = None
