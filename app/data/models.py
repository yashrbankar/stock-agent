from pydantic import BaseModel


class StockSnapshot(BaseModel):
    symbol: str
    company_name: str
    segment: str
    price: float | None = None
    fifty_two_week_low: float | None = None
    near_wkl_pct: float | None = None
    pe_ratio: float | None = None


class AnalysisResult(BaseModel):
    symbol: str
    company_name: str
    segment: str
    pe_ratio: float | None = None
    business_summary: str
    valuation_view: str
    profitability_view: str
    shareholding_view: str
    key_points: list[str]
    risks: list[str]
    raw_text: str


class PipelineRunResult(BaseModel):
    scanned_count: int
    near_low_stocks: list[StockSnapshot]
    analyses: list[AnalysisResult]
    gemini_failed: bool = False
    gemini_failure_reason: str = ""
