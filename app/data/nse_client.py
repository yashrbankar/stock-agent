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
            if self.settings.nse_index_name.upper() == "ALL NSE":
                response = client.get(
                    f"{self.BASE_URL}/api/market-data-pre-open",
                    params={"key": "ALL"},
                )
            else:
                response = client.get(
                    f"{self.BASE_URL}/api/equity-stockIndices",
                    params={"index": self.settings.nse_index_name},
                )
            response.raise_for_status()
            payload = response.json()

        records = payload.get("data", [])
        cleaned = []
        if self.settings.nse_index_name.upper() == "ALL NSE":
            for item in records:
                metadata = item.get("metadata", {})
                symbol = metadata.get("symbol")
                series = metadata.get("series")
                if not symbol or series != "EQ" or "-RE" in symbol or symbol.endswith("-BZ"):
                    continue
                cleaned.append(
                    {
                        "symbol": symbol,
                        "company_name": metadata.get("symbol"),
                        "payload": metadata,
                    }
                )
        else:
            for item in records:
                symbol = item.get("symbol")
                name = item.get("meta", {}).get("companyName") or item.get("identifier") or symbol
                if not symbol or symbol == self.settings.nse_index_name:
                    continue
                cleaned.append({"symbol": symbol, "company_name": name, "payload": item})

            cleaned.sort(key=lambda record: _near_wkl_sort_key(record["payload"]))

        logger.info("Fetched %s NSE symbols for %s", len(cleaned), self.settings.nse_index_name)
        return cleaned


def _near_wkl_sort_key(payload: dict) -> float:
    value = payload.get("nearWKL")
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 999999.0
