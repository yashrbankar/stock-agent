from app.config import get_settings
from app.data.models import StockSnapshot


def filter_candidates(stocks: list[StockSnapshot]) -> list[StockSnapshot]:
    settings = get_settings()
    max_near_low = _as_ratio(settings.bucket_2_near_wkl_pct)
    max_30d_change = _as_ratio(settings.filter_max_30d_change)
    min_365d_change = _as_ratio(settings.filter_min_365d_change)
    min_traded_value = settings.filter_min_traded_value_cr * 10_000_000
    filtered: list[StockSnapshot] = []

    for stock in stocks:
        if stock.near_wkl_pct is None or stock.near_wkl_pct > max_near_low:
            continue
        if stock.thirty_day_change is not None and stock.thirty_day_change > max_30d_change:
            continue
        if stock.one_year_change is not None and stock.one_year_change < min_365d_change:
            continue
        if stock.traded_value is not None and stock.traded_value < min_traded_value:
            continue
        filtered.append(stock)

    return sorted(filtered, key=_screen_rank)


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
    return sorted(
        selected,
        key=lambda stock: stock.near_wkl_pct if stock.near_wkl_pct is not None else 999,
    )


def _as_ratio(value: float) -> float:
    return value / 100 if value > 1 else value


def _screen_rank(stock: StockSnapshot) -> tuple[float, float, float, float]:
    near_low = stock.near_wkl_pct if stock.near_wkl_pct is not None else 999.0
    thirty_day = stock.thirty_day_change if stock.thirty_day_change is not None else 999.0
    one_year = -(stock.one_year_change if stock.one_year_change is not None else -999.0)
    traded_value = -(stock.traded_value if stock.traded_value is not None else 0.0)
    return (near_low, thirty_day, one_year, traded_value)
