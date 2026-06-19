"""Detect and store country/city for tournaments based on their name field.

Processes tournaments with country IS NULL (idempotent — safe to re-run).
Sources 'mol' and 'webcam' are skipped (no physical location).

Manual overrides are loaded from db/location_overrides.json (created automatically
on first run). Edit that file to assign country/city to any tournament by ID.

Usage:
    python db/detect_location.py [path/to/premodern.db] [--dry-run] [--stats]
                                  [--list-unknown [N]] [--reprocess]

Options:
    --dry-run        Show first 50 detections without writing to DB
    --stats          Print country counts after processing
    --list-unknown   List Unknown/unprocessed paper tournaments grouped by name
                     (pass a number after to limit rows, default 200)
    --reprocess      Re-run detection on already-set tournaments too (useful after
                     adding new rules or overrides)
"""

import json
import sqlite3
import sys
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# OVERRIDES FILE
# db/location_overrides.json  —  edit this file to assign locations manually.
# Format: { "tournament_id": {"country": "Argentina", "city": "Buenos Aires"}, ... }
# Keys are strings (JSON), values are objects with "country" and optional "city".
# ──────────────────────────────────────────────────────────────────────────────
OVERRIDES_FILE = Path(__file__).resolve().parent / "location_overrides.json"

OVERRIDES_TEMPLATE = {
    "_instructions": (
        "Add entries keyed by tournament ID (as string). "
        "Each entry needs 'country' and optionally 'city'. "
        "Run detect_location.py --reprocess to apply changes to already-set tournaments."
    ),
    "_example": {
        "12345": {"country": "Argentina", "city": "Buenos Aires"},
        "67890": {"country": "Spain", "city": "Madrid"},
    },
}


def load_overrides() -> dict[int, tuple[str, str | None]]:
    """Load location_overrides.json, creating it with a template if it doesn't exist."""
    if not OVERRIDES_FILE.exists():
        with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(OVERRIDES_TEMPLATE, f, ensure_ascii=False, indent=2)
        print(f"[info] Creado {OVERRIDES_FILE} — editalo para agregar overrides manuales.")
        return {}
    with open(OVERRIDES_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    overrides = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        try:
            overrides[int(k)] = (v["country"], v.get("city"))
        except (ValueError, KeyError):
            print(f"[warn] Override inválido ignorado: {k!r} → {v!r}")
    return overrides


# In-code overrides (legacy — prefer location_overrides.json)
MANUAL_OVERRIDES: dict[int, tuple[str, str | None]] = {}


# ──────────────────────────────────────────────────────────────────────────────
# DETECTION RULES
# Each entry: (country, [keyword_patterns], {keyword: city})
# Patterns are matched against name.lower(). First match wins.
# ──────────────────────────────────────────────────────────────────────────────
RULES: list[tuple[str, list[str], dict[str, str]]] = [
    ("Argentina", [
        "argentina", "buenos aires", "neuqu", "la plata", "magic lair",
        "bazaar of baghdad", "confluencia", "citadel", "mtg pirulo",
        "rosario", "córdoba", "cordoba", "mendoza", "tucumán", "tucuman",
        "santa fe", "mar del plata",
    ], {
        "buenos aires": "Buenos Aires",
        "neuqu": "Neuquén",
        "la plata": "La Plata",
        "rosario": "Rosario",
        "córdoba": "Córdoba",
        "cordoba": "Córdoba",
        "mendoza": "Mendoza",
        "tucumán": "Tucumán",
        "tucuman": "Tucumán",
        "santa fe": "Santa Fe",
        "mar del plata": "Mar del Plata",
    }),
    ("Spain", [
        "spain", "spanish", "españa", "espana", "tecnoliga", "liga madrileña", "liga madrilena",
        "liga premodern", "alicante", "valencia", "madrid", "bilbao", "mallorca",
        "granada", "sevilla", "barcelona", "zaragoza", "murcia", "extremadura",
        "galicia", "asturias", "cantabria", "navarra",
    ], {
        "alicante": "Alicante",
        "valencia": "Valencia",
        "madrid": "Madrid",
        "liga madrileña": "Madrid",
        "liga madrilena": "Madrid",
        "bilbao": "Bilbao",
        "mallorca": "Mallorca",
        "granada": "Granada",
        "sevilla": "Sevilla",
        "barcelona": "Barcelona",
        "zaragoza": "Zaragoza",
        "murcia": "Murcia",
        "extremadura": "Extremadura",
        "galicia": "Galicia",
    }),
    ("Italy", [
        "italy", "italian", "italia", "lega", "milano", "roma", "bologna",
        "genova", "rovereto", "brescia", "tappa", "napoli", "torino", "firenze",
        "venezia", "padova", "verona", "trieste", "bari", "catania",
        "magico conclave", "monthly italian", "reggio emil", "ravenna",
        "arzan premodern",
    ], {
        "milano": "Milano",
        "roma": "Roma",
        "bologna": "Bologna",
        "genova": "Genova",
        "rovereto": "Rovereto",
        "brescia": "Brescia",
        "napoli": "Napoli",
        "torino": "Torino",
        "firenze": "Firenze",
        "venezia": "Venezia",
        "padova": "Padova",
        "verona": "Verona",
        "trieste": "Trieste",
        "bari": "Bari",
        "catania": "Catania",
    }),
    ("Germany", [
        "germany", "german", "berlin", "nuremberg", "nürnberg", "essen",
        "mainz", "unperfekthaus", "münchen", "munchen", "hamburg", "köln",
        "koln", "frankfurt", "stuttgart", "dortmund", "düsseldorf", "dusseldorf",
        "leipzig", "dresden", " germany", "(germany",
    ], {
        "berlin": "Berlin",
        "nuremberg": "Nuremberg",
        "nürnberg": "Nuremberg",
        "essen": "Essen",
        "mainz": "Mainz",
        "münchen": "München",
        "munchen": "München",
        "hamburg": "Hamburg",
        "köln": "Köln",
        "koln": "Köln",
        "frankfurt": "Frankfurt",
        "stuttgart": "Stuttgart",
        "dortmund": "Dortmund",
        "düsseldorf": "Düsseldorf",
        "dusseldorf": "Düsseldorf",
        "leipzig": "Leipzig",
        "dresden": "Dresden",
    }),
    ("Brazil", [
        "brazil", "brasil", "são paulo", "sao paulo", "fortaleza", "paulista",
        "rio de janeiro", "belo horizonte", "curitiba", "recife", "porto alegre",
        "polar jogos", "liga paulista",
    ], {
        "são paulo": "São Paulo",
        "sao paulo": "São Paulo",
        "fortaleza": "Fortaleza",
        "rio de janeiro": "Rio de Janeiro",
        "belo horizonte": "Belo Horizonte",
        "curitiba": "Curitiba",
        "recife": "Recife",
        "porto alegre": "Porto Alegre",
    }),
    ("Portugal", [
        "portugal", "portuguese", "lisbon", "lisboa", "covilhã", "covilha",
        "porto", "braga", "faro",
    ], {
        "lisbon": "Lisbon",
        "lisboa": "Lisbon",
        "covilhã": "Covilhã",
        "covilha": "Covilhã",
        "porto": "Porto",
        "braga": "Braga",
        "faro": "Faro",
    }),
    ("France", [
        "france", "french", "paris", "lyon", "marseille", "bordeaux",
        "toulouse", "nantes", "strasbourg", "montpellier",
    ], {
        "paris": "Paris",
        "lyon": "Lyon",
        "marseille": "Marseille",
        "bordeaux": "Bordeaux",
        "toulouse": "Toulouse",
        "nantes": "Nantes",
        "strasbourg": "Strasbourg",
        "montpellier": "Montpellier",
    }),
    ("Netherlands", [
        "netherlands", "dutch", "amsterdam", "rotterdam", "utrecht",
        "eindhoven", "den haag", "the hague",
    ], {
        "amsterdam": "Amsterdam",
        "rotterdam": "Rotterdam",
        "utrecht": "Utrecht",
        "eindhoven": "Eindhoven",
        "den haag": "Den Haag",
        "the hague": "Den Haag",
    }),
    ("Finland", [
        "finland", "finnish", "helsinki", "mätkymökki", "matkymokki", "tampere", "turku",
    ], {
        "helsinki": "Helsinki",
        "tampere": "Tampere",
        "turku": "Turku",
    }),
    ("Sweden", [
        "sweden", "swedish", "stockholm", "göteborg", "goteborg", "malmö", "malmo",
        "norrlands",
    ], {
        "stockholm": "Stockholm",
        "göteborg": "Göteborg",
        "goteborg": "Göteborg",
        "malmö": "Malmö",
        "malmo": "Malmö",
    }),
    ("USA", [
        "portland", "philadelphia", "bellingham", "minneapolis", "chicago",
        "new york", "los angeles", "seattle", "boston", "detroit",
        ", nh)", ", ma)", ", md)", ", mn)", ", ca)", ", mi)", ", wa)",
        ", ny)", ", tx)", ", fl)", ", oh)", ", il)", ", pa)",
        "newington", "worcester",
    ], {
        "portland": "Portland, OR",
        "philadelphia": "Philadelphia, PA",
        "bellingham": "Bellingham, WA",
        "minneapolis": "Minneapolis, MN",
        "chicago": "Chicago, IL",
        "new york": "New York, NY",
        "los angeles": "Los Angeles, CA",
        "seattle": "Seattle, WA",
        "boston": "Boston, MA",
        "detroit": "Detroit, MI",
        "newington": "Newington, NH",
    }),
    ("Singapore", [
        "singapore",
    ], {
        "singapore": "Singapore",
    }),
    ("Philippines", [
        "philippines", "manila", "filipino",
    ], {
        "manila": "Manila",
    }),
    ("Australia", [
        "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide",
    ], {
        "sydney": "Sydney",
        "melbourne": "Melbourne",
        "brisbane": "Brisbane",
        "perth": "Perth",
        "adelaide": "Adelaide",
    }),
    ("United Kingdom", [
        "england", "uk premodern", "london", "manchester", "birmingham",
        "edinburgh", "glasgow", "bristol",
    ], {
        "london": "London",
        "manchester": "Manchester",
        "birmingham": "Birmingham",
        "edinburgh": "Edinburgh",
        "glasgow": "Glasgow",
        "bristol": "Bristol",
    }),
]


def detect_location(name: str) -> tuple[str, str | None]:
    """Return (country, city) for a tournament name. Falls back to ('Unknown', None)."""
    name_lower = name.lower()
    for country, keywords, city_map in RULES:
        for kw in keywords:
            if kw in name_lower:
                city = None
                # Try all city keywords, pick most specific (longest match)
                best = ""
                for ck, cv in city_map.items():
                    if ck in name_lower and len(ck) > len(best):
                        best = ck
                        city = cv
                return country, city
    return "Unknown", None


def ensure_schema(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tournaments)").fetchall()}
    for col in ("country", "city"):
        if col not in existing:
            conn.execute(f"ALTER TABLE tournaments ADD COLUMN {col} TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tournaments_country ON tournaments(country)"
    )
    conn.commit()


def list_unknown(conn: sqlite3.Connection, limit: int = 200) -> None:
    """Print Unknown/unprocessed tournaments grouped by name prefix for easy manual override."""
    rows = conn.execute(
        """SELECT id, name, date, player_count
           FROM tournaments
           WHERE source = 'paper' AND (country IS NULL OR country = 'Unknown')
           ORDER BY name, date"""
    ).fetchall()

    if not rows:
        print("No hay torneos sin ubicacion identificada.")
        return

    print(f"\nTorneos sin ubicacion ({len(rows):,} total) — primeros {limit}")
    print(f"{'ID':>7}  {'Fecha':<12}  {'Jug':>4}  Nombre")
    print("-" * 72)
    shown = 0
    prev_prefix = ""
    for tid, name, date, players in rows:
        if shown >= limit:
            break
        prefix = name[:35]
        if prefix != prev_prefix and shown > 0:
            print()  # blank line between groups
        prev_prefix = prefix
        print(f"{tid:>7}  {date:<12}  {(players or 0):>4}  {name[:55]}")
        shown += 1

    print(f"\nPara asignar ubicacion, edita: {OVERRIDES_FILE}")
    print('Formato: { "ID": {"country": "Argentina", "city": "Buenos Aires"} }')
    print("Luego corre: python db/detect_location.py db/premodern.db --reprocess")


def process(conn: sqlite3.Connection, dry_run: bool = False,
            reprocess: bool = False) -> list[tuple]:
    overrides = {**MANUAL_OVERRIDES, **load_overrides()}

    where = "source = 'paper'" if reprocess else "country IS NULL AND source = 'paper'"
    rows = conn.execute(
        f"SELECT id, name, source FROM tournaments WHERE {where} ORDER BY date"
    ).fetchall()

    results = []
    for tid, name, source in rows:
        if tid in overrides:
            country, city = overrides[tid]
        else:
            country, city = detect_location(name)
        results.append((tid, name, country, city))

    if dry_run:
        print(f"\n{'ID':>6}  {'Pais':<15}  {'Ciudad':<20}  Nombre")
        print("-" * 80)
        for tid, name, country, city in results[:50]:
            print(f"{tid:>6}  {country:<15}  {(city or '-'):<20}  {name[:50]}")
        print(f"\nTotal a procesar: {len(results):,} torneos")
        return results

    for tid, _, country, city in results:
        conn.execute(
            "UPDATE tournaments SET country = ?, city = ? WHERE id = ?",
            (country, city, tid),
        )
    conn.commit()
    print(f"✓ {len(results):,} torneos actualizados.")
    return results


def print_stats(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """SELECT country, COUNT(*) as torneos,
                  SUM(player_count) as jugadores
           FROM tournaments
           WHERE country IS NOT NULL AND source = 'paper'
           GROUP BY country ORDER BY torneos DESC"""
    ).fetchall()
    print(f"\n{'País':<20}  {'Torneos':>8}  {'Jugadores':>10}")
    print("-" * 44)
    for country, torneos, jugadores in rows:
        print(f"{country:<20}  {torneos:>8,}  {jugadores or 0:>10,}")


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
    ensure_schema(conn)

    if "--list-unknown" in flags:
        limit = int(positional[1]) if len(positional) > 1 else 200
        list_unknown(conn, limit=limit)
    else:
        process(conn,
                dry_run="--dry-run" in flags,
                reprocess="--reprocess" in flags)
        if "--stats" in flags or "--dry-run" not in flags:
            print_stats(conn)

    conn.close()


if __name__ == "__main__":
    main()
