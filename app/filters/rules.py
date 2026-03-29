from app.config import get_settings
from app.data.models import StockSnapshot


def filter_candidates(stocks: list[StockSnapshot]) -> list[StockSnapshot]:
    settings = get_settings()
    filtered: list[StockSnapshot] = []

    for stock in stocks:
        if stock.near_wkl_pct is None or stock.near_wkl_pct > _as_ratio(settings.bucket_2_near_wkl_pct):
            continue
        if stock.pe is None or stock.pe >= settings.filter_max_pe:
            continue
        if stock.pb is None or stock.pb >= settings.filter_max_pb:
            continue
        if stock.debt_to_equity is None or stock.debt_to_equity >= settings.filter_max_debt_to_equity:
            continue
        if stock.thirty_day_change is None or stock.thirty_day_change >= settings.filter_max_30d_change:
            continue
        filtered.append(stock)

    return filtered


def select_near_low_stocks(
    stocks: list[StockSnapshot],
    *,
    max_threshold: float,
    min_threshold: float = 0.0,
) -> list[StockSnapshot]:
    min_ratio = _as_ratio(min_threshold)
    max_ratio = _as_ratio(max_threshold)
    selected = [
        stock
        for stock in stocks
        if stock.near_wkl_pct is not None
        and (
            min_ratio <= stock.near_wkl_pct <= max_ratio
            if min_threshold == 0
            else min_ratio < stock.near_wkl_pct <= max_ratio
        )
    ]
    return sorted(selected, key=lambda stock: stock.near_wkl_pct if stock.near_wkl_pct is not None else 999)


def _as_ratio(value: float) -> float:
    return value / 100 if value > 1 else value
