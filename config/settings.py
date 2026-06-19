from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db" / "premodern.db"

BASE_URL = "https://www.tcdecks.net"
RESULTS_URL = f"{BASE_URL}/results.php"
DECK_URL = f"{BASE_URL}/deck.php"
ARCHETYPE_URL = f"{BASE_URL}/archetype.php"
FORMAT = "Premodern"

RESULTS_PER_PAGE = 30

DELAY_HTTP = 1.5
DELAY_PLAYWRIGHT = 2.5
MAX_RETRIES = 3
RETRY_BACKOFF = 2
REQUEST_TIMEOUT = 30
MAX_CONCURRENT_BROWSERS = 2
BATCH_SIZE = 100

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
