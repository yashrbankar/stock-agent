from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.dependencies import stock_service
from app.scheduler.jobs import create_scheduler
from app.utils.logging import configure_logging


configure_logging()
settings = get_settings()
scheduler = create_scheduler(stock_service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not scheduler.running:
        scheduler.start()
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
