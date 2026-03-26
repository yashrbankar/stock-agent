import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.services.stock_service import StockService


logger = logging.getLogger(__name__)


def create_scheduler(service: StockService) -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        func=lambda: _run_job(service),
        trigger="cron",
        hour=settings.schedule_hour,
        minute=settings.schedule_minute,
        id="daily-stock-scan",
        replace_existing=True,
    )
    return scheduler


def _run_job(service: StockService) -> None:
    logger.info("Starting scheduled stock pipeline.")
    try:
        service.run_pipeline()
    except Exception:
        logger.exception("Scheduled stock pipeline failed.")
