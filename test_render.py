from app.services.stock_service import StockService
from app.data.models import PipelineRunResult, StockSnapshot, AnalysisResult
svc = StockService()
res = PipelineRunResult(
    scanned_count=100,
    near_low_stocks=[
        StockSnapshot(symbol="AAPL", company_name="Apple", segment="NIFTY 100", pe_ratio=15, price=150, near_wkl_pct=0.05)
    ],
    analyses=[],
    market_news="Some *bold* and #heading news",
    applied_pct=5.0
)
with open("test.html", "w") as f:
    f.write(svc._build_html_report(res))
print("Wrote test.html")
