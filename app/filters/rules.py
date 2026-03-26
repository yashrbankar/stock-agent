from app.config import get_settings
from app.data.models import StockSnapshot


def filter_candidates(stocks: list[StockSnapshot]) -> list[StockSnapshot]:
    settings = get_settings()
    filtered: list[StockSnapshot] = []

    for stock in stocks:
        if stock.near_wkl_pct is None or stock.near_wkl_pct > settings.filter_near_wkl_pct:
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
