import logging
from collections.abc import Iterable

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
            cleaned_by_symbol: dict[str, dict] = {}
            for index_name in self.settings.nse_index_names:
                for record in self._fetch_equity_symbols_for_index(client, index_name):
                    cleaned_by_symbol[record["symbol"]] = record

        cleaned = list(cleaned_by_symbol.values())
        cleaned.sort(key=lambda record: _near_wkl_sort_key(record["payload"]))

        logger.info(
            "Fetched %s unique NSE symbols across %s",
            len(cleaned),
            self.settings.nse_universe_label,
        )
        return cleaned

    @retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3), reraise=True)
    def fetch_pe_ratios(self, symbols: list[str]) -> dict[str, float | None]:
        pe_by_symbol: dict[str, float | None] = {}
        with httpx.Client(timeout=20.0, headers=self.headers, follow_redirects=True) as client:
            for symbol in symbols:
                response = client.get(
                    f"{self.BASE_URL}/api/quote-equity",
                    params={"symbol": symbol},
                )
                response.raise_for_status()
                payload = response.json()
                pe_by_symbol[symbol] = _float_or_none(
                    payload.get("metadata", {}).get("pdSymbolPe")
                )
        return pe_by_symbol

    def _fetch_equity_symbols_for_index(
        self,
        client: httpx.Client,
        index_name: str,
    ) -> Iterable[dict]:
        if index_name.upper() == "ALL NSE":
            response = client.get(
                f"{self.BASE_URL}/api/market-data-pre-open",
                params={"key": "ALL"},
            )
            response.raise_for_status()
            payload = response.json()
            return self._clean_all_nse_records(payload.get("data", []), index_name)

        response = client.get(
            f"{self.BASE_URL}/api/equity-stockIndices",
            params={"index": index_name},
        )
        response.raise_for_status()
        payload = response.json()
        return self._clean_index_records(payload.get("data", []), index_name)

    def _clean_all_nse_records(self, records: list[dict], index_name: str) -> list[dict]:
        cleaned = []
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
                    "payload": {**metadata, "sourceIndex": index_name},
                }
            )
        return cleaned

    def _clean_index_records(self, records: list[dict], index_name: str) -> list[dict]:
        cleaned = []
        for item in records:
            symbol = item.get("symbol")
            name = item.get("meta", {}).get("companyName") or item.get("identifier") or symbol
            if not symbol or symbol == index_name:
                continue
            cleaned.append(
                {
                    "symbol": symbol,
                    "company_name": name,
                    "payload": {**item, "sourceIndex": index_name},
                }
            )
        return cleaned


def _near_wkl_sort_key(payload: dict) -> float:
    value = payload.get("nearWKL")
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 999999.0


def _float_or_none(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
