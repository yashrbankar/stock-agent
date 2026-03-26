from app.services.stock_service import StockService


stock_service = StockService()


def get_stock_service() -> StockService:
    return stock_service
