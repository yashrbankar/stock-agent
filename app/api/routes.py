from fastapi import APIRouter, Depends, HTTPException

from app.data.models import PipelineRunResult, StockSnapshot
from app.dependencies import get_stock_service
from app.services.stock_service import StockService


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stocks", response_model=list[StockSnapshot])
def get_stocks(service: StockService = Depends(get_stock_service)) -> list[StockSnapshot]:
    return service.list_filtered_stocks()


@router.get("/run", response_model=PipelineRunResult)
def run_pipeline(service: StockService = Depends(get_stock_service)) -> PipelineRunResult:
    try:
        return service.run_pipeline()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
