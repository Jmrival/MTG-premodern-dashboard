import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BaseScraper:
    def __init__(self, delay: float = 1.5, max_retries: int = 3,
                 backoff_factor: float = 2, timeout: int = 30,
                 user_agent: str = None):
        self.delay = delay
        self.timeout = timeout
        self._last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        })

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def get(self, url: str, params: dict = None) -> requests.Response:
        self._rate_limit()
        logger.debug(f"GET {url} params={params}")
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response
