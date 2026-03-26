import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings


logger = logging.getLogger(__name__)


class NSEClient:
    BASE_URL = "https://www.nseindia.com"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        }

    @retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3), reraise=True)
    def fetch_equity_symbols(self) -> list[dict]:
        with httpx.Client(timeout=20.0, headers=self.headers, follow_redirects=True) as client:
            client.get(self.BASE_URL)
            response = client.get(
                f"{self.BASE_URL}/api/equity-stockIndices",
                params={"index": self.settings.nse_index_name},
            )
            response.raise_for_status()
            payload = response.json()

        records = payload.get("data", [])
        cleaned = []
        for item in records:
            symbol = item.get("symbol")
            name = item.get("meta", {}).get("companyName") or item.get("identifier") or symbol
            if not symbol or symbol in {"NIFTY 500"}:
                continue
            cleaned.append({"symbol": symbol, "company_name": name, "payload": item})

        logger.info("Fetched %s NSE symbols for %s", len(cleaned), self.settings.nse_index_name)
        return cleaned[: self.settings.screen_limit]
