import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf

from app.config import get_settings
from app.data.models import StockSnapshot


logger = logging.getLogger(__name__)


class FundamentalsClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def build_snapshot(self, symbol: str, company_name: str, source_meta: dict) -> StockSnapshot | None:
        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info or {}

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.settings.lookback_days)
        history = ticker.history(start=start, end=end, auto_adjust=False)
        if history.empty:
            logger.warning("No price history found for %s", symbol)
            return None

        close_series = history["Close"].dropna()
        current_price = float(close_series.iloc[-1])
        fifty_two_week_low = float(close_series.min())
        month_anchor = close_series.iloc[-21] if len(close_series) > 21 else close_series.iloc[0]
        thirty_day_change = float((current_price - month_anchor) / month_anchor) if month_anchor else None
        near_wkl_pct = (
            float(((current_price - fifty_two_week_low) / fifty_two_week_low) * 100)
            if fifty_two_week_low
            else None
        )
        nse_near_wkl = _normalize_percent(source_meta.get("nearWKL"))
        nse_thirty_day_change = _normalize_percent(source_meta.get("perChange30d"))

        debt_raw = info.get("debtToEquity")
        debt_to_equity = float(debt_raw) / 100 if debt_raw is not None else None

        return StockSnapshot(
            symbol=symbol,
            company_name=company_name,
            price=current_price,
            fifty_two_week_low=fifty_two_week_low,
            near_wkl_pct=nse_near_wkl if nse_near_wkl is not None else near_wkl_pct,
            pe=_float_or_none(info.get("trailingPE")),
            pb=_float_or_none(info.get("priceToBook")),
            debt_to_equity=debt_to_equity,
            thirty_day_change=(
                nse_thirty_day_change if nse_thirty_day_change is not None else thirty_day_change
            ),
            market_cap=_float_or_none(info.get("marketCap")),
            source_meta={"nse": source_meta, "yfinance": _extract_debug_meta(info)},
        )


def _float_or_none(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _extract_debug_meta(info: dict) -> dict:
    keys = ("sector", "industry", "website", "longBusinessSummary")
    return {key: info.get(key) for key in keys if info.get(key)}


def _normalize_percent(value: object) -> float | None:
    numeric = _float_or_none(value)
    if numeric is None:
        return None
    return numeric / 100
