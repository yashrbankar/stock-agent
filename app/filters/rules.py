from app.config import get_settings
from app.data.models import StockSnapshot


def filter_candidates(stocks: list[StockSnapshot]) -> list[StockSnapshot]:
    """Keep only stocks that are near their 52-week low."""
    settings = get_settings()
    max_near_low = _as_ratio(settings.near_52_week_low_pct)
    filtered = [
        stock
        for stock in stocks
        if stock.near_wkl_pct is not None and stock.near_wkl_pct <= max_near_low
    ]
    return sorted(filtered, key=_near_low_rank)


def _as_ratio(value: float) -> float:
    return value / 100 if value > 1 else value


def _near_low_rank(stock: StockSnapshot) -> float:
    return stock.near_wkl_pct if stock.near_wkl_pct is not None else 999.0
