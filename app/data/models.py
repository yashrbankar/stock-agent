from typing import Any

from pydantic import BaseModel, Field


class StockSnapshot(BaseModel):
    symbol: str
    company_name: str
    price: float | None = None
    fifty_two_week_low: float | None = None
    near_wkl_pct: float | None = None
    pe: float | None = None
    pb: float | None = None
    debt_to_equity: float | None = None
    thirty_day_change: float | None = None
    market_cap: float | None = None
    source_meta: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    symbol: str
    company_name: str
    reason: str
    risks: list[str]
    opportunity: str
    verdict: str
    raw_text: str


class PipelineRunResult(BaseModel):
    candidates: list[StockSnapshot]
    filtered: list[StockSnapshot]
    near_low_5_pct: list[StockSnapshot]
    near_low_10_pct: list[StockSnapshot]
    analyses: list[AnalysisResult]
    summary: str
    gemini_failed: bool = False
    gemini_failure_reason: str = ""
