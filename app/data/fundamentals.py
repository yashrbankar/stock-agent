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

        if near_wkl_pct is None and price is None:
            logger.warning("NSE payload for %s did not include usable market data", symbol)
            return None

        return StockSnapshot(
            symbol=symbol,
            company_name=company_name,
            segment=str(source_meta.get("sourceIndex", "Unknown")),
            price=price,
            fifty_two_week_low=fifty_two_week_low,
            near_wkl_pct=near_wkl_pct,
        )


def _float_or_none(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None

def _normalize_percent(value: object) -> float | None:
    numeric = _float_or_none(value)
    if numeric is None:
        return None
    return numeric / 100
