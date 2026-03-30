import logging

from app.config import get_settings
from app.data.models import StockSnapshot

logger = logging.getLogger(__name__)


class FundamentalsClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def build_snapshot(
        self,
        symbol: str,
        company_name: str,
        source_meta: dict,
    ) -> StockSnapshot | None:
        price = _float_or_none(source_meta.get("lastPrice"))
        fifty_two_week_low = _float_or_none(source_meta.get("yearLow"))
        near_wkl_pct = _normalize_percent(source_meta.get("nearWKL"))
        if near_wkl_pct is not None:
            near_wkl_pct = abs(near_wkl_pct)

        thirty_day_change = _normalize_percent(source_meta.get("perChange30d"))
        one_year_change = _normalize_percent(source_meta.get("perChange365d"))
        day_change = _normalize_percent(source_meta.get("pChange"))
        traded_value = _float_or_none(source_meta.get("totalTradedValue"))
        traded_volume = _float_or_none(source_meta.get("totalTradedVolume"))
        industry = _coerce_text(_nested_get(source_meta, "meta", "industry"))

        if near_wkl_pct is None and price is None:
            logger.warning("NSE payload for %s did not include usable market data", symbol)
            return None

        return StockSnapshot(
            symbol=symbol,
            company_name=company_name,
            industry=industry,
            price=price,
            fifty_two_week_low=fifty_two_week_low,
            near_wkl_pct=near_wkl_pct,
            day_change=day_change,
            one_year_change=one_year_change,
            traded_value=traded_value,
            traded_volume=traded_volume,
            thirty_day_change=thirty_day_change,
            source_meta={"nse": _extract_debug_meta(source_meta)},
        )


def _float_or_none(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _extract_debug_meta(info: dict) -> dict:
    keys = (
        "symbol",
        "identifier",
        "lastPrice",
        "yearLow",
        "nearWKL",
        "perChange30d",
        "perChange365d",
        "totalTradedValue",
    )
    payload = {key: info.get(key) for key in keys if info.get(key) is not None}
    meta = info.get("meta")
    if isinstance(meta, dict):
        payload["meta"] = {
            key: meta.get(key)
            for key in ("companyName", "industry", "listingDate", "isFNOSec")
            if meta.get(key) is not None
        }
    return payload


def _normalize_percent(value: object) -> float | None:
    numeric = _float_or_none(value)
    if numeric is None:
        return None
    return numeric / 100


def _nested_get(payload: dict, *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _coerce_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
