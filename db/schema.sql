PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    date DATE NOT NULL,
    player_count INTEGER,
    source TEXT CHECK(source IN ('paper', 'webcam', 'mol', 'unknown')) DEFAULT 'unknown',
    format TEXT NOT NULL DEFAULT 'premodern',  -- ej. 'premodern', 'oldschool', 'vintage'
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tournaments_date ON tournaments(date);
CREATE INDEX IF NOT EXISTS idx_tournaments_source ON tournaments(source);
CREATE INDEX IF NOT EXISTS idx_tournaments_format ON tournaments(format);

CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    player_name TEXT NOT NULL,
    archetype TEXT NOT NULL,
    archetype_url TEXT,
    position INTEGER,
    total_players INTEGER,
    date DATE NOT NULL,
    cards_scraped BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_decks_tournament ON decks(tournament_id);
CREATE INDEX IF NOT EXISTS idx_decks_archetype ON decks(archetype);
CREATE INDEX IF NOT EXISTS idx_decks_player ON decks(player_name);
CREATE INDEX IF NOT EXISTS idx_decks_date ON decks(date);
CREATE INDEX IF NOT EXISTS idx_decks_unscraped ON decks(cards_scraped) WHERE cards_scraped = 0;

CREATE TABLE IF NOT EXISTS cards (
    name TEXT PRIMARY KEY,
    card_type TEXT,
    cardmarket_id INTEGER,
    cardmarket_url TEXT,
    -- Datos de Scryfall (ver db/sync_scryfall.py)
    mana_cost TEXT,
    cmc REAL,
    type_line TEXT,
    oracle_text TEXT,
    flavor_text TEXT,
    power TEXT,
    toughness TEXT,
    loyalty TEXT,
    colors TEXT,            -- ej. "R,G" (vacio = incolora)
    color_identity TEXT,
    keywords TEXT,           -- ej. "Flying,Trample"
    produced_mana TEXT,
    rarity TEXT,
    set_code TEXT,
    set_name TEXT,
    released_at TEXT,
    collector_number TEXT,
    layout TEXT,
    image_uri TEXT,
    scryfall_id TEXT,
    price_usd REAL,          -- precio mas economico disponible (snapshot vigente)
    price_updated_at TIMESTAMP,
    scryfall_raw TEXT,        -- payload JSON completo devuelto por Scryfall (por si se necesita algo no extraido arriba)
    scryfall_synced_at TIMESTAMP
);

-- Historial de precios: cada corrida de refresh agrega una fila por carta,
-- para poder analizar la evolucion del precio en el tiempo.
CREATE TABLE IF NOT EXISTS card_price_history (
    card_name TEXT NOT NULL REFERENCES cards(name),
    price_usd REAL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (card_name, fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_price_history_card ON card_price_history(card_name);

CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id INTEGER NOT NULL REFERENCES decks(id),
    card_name TEXT NOT NULL REFERENCES cards(name),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    is_sideboard BOOLEAN NOT NULL DEFAULT 0,
    PRIMARY KEY (deck_id, card_name, is_sideboard)
);

CREATE INDEX IF NOT EXISTS idx_deck_cards_card ON deck_cards(card_name);
CREATE INDEX IF NOT EXISTS idx_deck_cards_deck ON deck_cards(deck_id);

CREATE TABLE IF NOT EXISTS scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase TEXT NOT NULL,
    last_page INTEGER,
    total_new_records INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT CHECK(status IN ('running', 'completed', 'failed')) DEFAULT 'running'
);

CREATE VIEW IF NOT EXISTS v_meta_share AS
SELECT
    t.format,
    d.archetype,
    strftime('%Y-%m', d.date) AS month,
    COUNT(*) AS deck_count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (
        PARTITION BY t.format, strftime('%Y-%m', d.date)
    ) AS meta_share_pct
FROM decks d
JOIN tournaments t ON t.id = d.tournament_id
GROUP BY t.format, d.archetype, strftime('%Y-%m', d.date);

CREATE VIEW IF NOT EXISTS v_archetype_success AS
SELECT
    t.format,
    d.archetype,
    COUNT(*) AS total_entries,
    AVG(CASE WHEN d.position <= 8 THEN 1.0 ELSE 0.0 END) AS top8_rate,
    AVG(CASE WHEN d.position <= 4 THEN 1.0 ELSE 0.0 END) AS top4_rate,
    AVG(CASE WHEN d.position = 1 THEN 1.0 ELSE 0.0 END) AS win_rate,
    AVG(d.position * 1.0 / d.total_players) AS avg_relative_position
FROM decks d
JOIN tournaments t ON t.id = d.tournament_id
WHERE d.total_players >= 8
GROUP BY t.format, d.archetype
HAVING COUNT(*) >= 10;

CREATE VIEW IF NOT EXISTS v_card_popularity AS
SELECT
    t.format,
    dc.card_name,
    dc.is_sideboard,
    COUNT(DISTINCT dc.deck_id) AS deck_count,
    SUM(dc.quantity) AS total_copies,
    AVG(dc.quantity) AS avg_copies_per_deck
FROM deck_cards dc
JOIN decks d ON d.id = dc.deck_id
JOIN tournaments t ON t.id = d.tournament_id
GROUP BY t.format, dc.card_name, dc.is_sideboard;

CREATE VIEW IF NOT EXISTS v_player_stats AS
SELECT
    t.format,
    d.player_name,
    COUNT(*)                                              AS total_entradas,
    COUNT(DISTINCT d.tournament_id)                       AS torneos_jugados,
    COUNT(DISTINCT d.archetype)                           AS arquetipos_distintos,
    SUM(CASE WHEN d.position = 1   THEN 1 ELSE 0 END)    AS victorias,
    SUM(CASE WHEN d.position <= 4  THEN 1 ELSE 0 END)    AS top4s,
    SUM(CASE WHEN d.position <= 8  THEN 1 ELSE 0 END)    AS top8s,
    ROUND(AVG(d.position * 1.0 / d.total_players), 4)    AS avg_posicion_relativa,
    ROUND(
        SUM(CASE WHEN d.position <= 8 THEN 1.0 ELSE 0.0 END) / COUNT(*), 4
    )                                                     AS top8_rate,
    MIN(d.date)                                           AS primer_torneo,
    MAX(d.date)                                           AS ultimo_torneo
FROM decks d
JOIN tournaments t ON t.id = d.tournament_id
WHERE d.total_players >= 8
GROUP BY t.format, d.player_name
HAVING COUNT(*) >= 3;
