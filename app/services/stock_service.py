import logging
import os

from app.config import get_settings
from app.analysis.gemini_client import GeminiAnalyzer
from app.data.fundamentals import FundamentalsClient
from app.data.models import PipelineRunResult, StockSnapshot
from app.data.nse_client import NSEClient
from app.filters.rules import filter_candidates, select_near_low_stocks
from app.notification.emailer import EmailNotifier
from app.notification.whatsapp import WhatsAppNotifier


logger = logging.getLogger(__name__)


class StockService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.nse_client = NSEClient()
        self.fundamentals_client = FundamentalsClient()
        self.analyzer = GeminiAnalyzer()
        self.email_notifier = EmailNotifier()
        self.whatsapp_notifier = WhatsAppNotifier()
        self._last_run: PipelineRunResult | None = None

    def list_filtered_stocks(self) -> list[StockSnapshot]:
        if self._last_run:
            return self._last_run.filtered

        candidates = self._load_candidates()
        return filter_candidates(candidates)

    def run_pipeline(self, notify: bool = True) -> PipelineRunResult:
        candidates = self._load_candidates()
        filtered = filter_candidates(candidates)
        near_low_5_pct = select_near_low_stocks(
            candidates,
            max_threshold=self.settings.bucket_1_near_wkl_pct,
        )
        near_low_10_pct = select_near_low_stocks(
            candidates,
            min_threshold=self.settings.bucket_1_near_wkl_pct,
            max_threshold=self.settings.bucket_2_near_wkl_pct,
        )
        near_low_20_pct = select_near_low_stocks(
            candidates,
            min_threshold=self.settings.bucket_2_near_wkl_pct,
            max_threshold=self.settings.bucket_3_near_wkl_pct,
        )

        analyses: list = []
        summary = "No qualifying stocks today."
        gemini_failed = False
        gemini_failure_reason = ""
        if filtered:
            try:
                analyses = [self.analyzer.analyze(stock) for stock in filtered]
                summary = self.analyzer.summarize(analyses) if analyses else "No qualifying stocks today."
            except Exception as exc:
                gemini_failed = True
                gemini_failure_reason = str(exc)
                summary = (
                    "Gemini analysis is not available right now. "
                    "Still sharing the near 52-week low stock lists below."
                )
                logger.exception("Gemini analysis failed. Falling back to near-low stock lists only.")

        result = PipelineRunResult(
            candidates=candidates,
            filtered=filtered,
            near_low_5_pct=near_low_5_pct,
            near_low_10_pct=near_low_10_pct,
            near_low_20_pct=near_low_20_pct,
            analyses=analyses,
            summary=summary,
            gemini_failed=gemini_failed,
            gemini_failure_reason=gemini_failure_reason,
        )
        self._last_run = result

        report = self._build_report(result)
        if notify:
            self.email_notifier.send("Daily Stock Bot Report", report)
            self.whatsapp_notifier.send(report)
        else:
            print(report)

        return result

    def _load_candidates(self) -> list[StockSnapshot]:
        records = self.nse_client.fetch_equity_symbols()
        snapshots: list[StockSnapshot] = []
        for item in records:
            snapshot = self.fundamentals_client.build_snapshot(
                symbol=item["symbol"],
                company_name=item["company_name"],
                source_meta=item["payload"],
            )
            if snapshot:
                snapshots.append(snapshot)
        logger.info("Built %s stock snapshots", len(snapshots))
        return snapshots

    def _build_report(self, result: PipelineRunResult) -> str:
        lines = [
            "Daily Stock Bot Report",
            "",
            f"Run revision: {os.getenv('GITHUB_SHA', 'local')[:7]}",
            "",
            f"Universe: {self.settings.nse_index_name}",
            "",
            f"Candidates scanned: {len(result.candidates)}",
            f"After filters: {len(result.filtered)}",
            "",
            "Executive Summary",
            result.summary,
            "",
            f"Near 52-Week Low: Within {self.settings.bucket_1_near_wkl_pct}%",
            self._render_stock_table(result.near_low_5_pct),
            "",
            (
                f"Near 52-Week Low: More than {self.settings.bucket_1_near_wkl_pct}% "
                f"and up to {self.settings.bucket_2_near_wkl_pct}%"
            ),
            self._render_stock_table(result.near_low_10_pct),
            "",
            (
                f"Near 52-Week Low: More than {self.settings.bucket_2_near_wkl_pct}% "
                f"and up to {self.settings.bucket_3_near_wkl_pct}%"
            ),
            self._render_stock_table(result.near_low_20_pct),
            "",
            "Detailed Analyses",
        ]

        if result.gemini_failed:
            lines.extend(
                [
                    "Gemini Status",
                    "Gemini analysis failed in this run.",
                    f"Reason: {result.gemini_failure_reason}",
                    "",
                ]
            )

        for analysis in result.analyses:
            lines.extend(
                [
                    f"- {analysis.symbol} ({analysis.company_name})",
                    f"  Verdict: {analysis.verdict}",
                    f"  Reason: {analysis.reason}",
                    f"  Opportunity: {analysis.opportunity}",
                    f"  Risks: {', '.join(analysis.risks) if analysis.risks else 'None listed'}",
                    "",
                ]
            )

        return "\n".join(lines)

    def _render_stock_table(self, stocks: list[StockSnapshot]) -> str:
        if not stocks:
            return "No stocks in this section."

        headers = ("Symbol", "Company", "Price", "Near Low")
        rows = [headers]
        for stock in stocks:
            rows.append(
                (
                    stock.symbol,
                    stock.company_name,
                    self._fmt_currency(stock.price),
                    self._fmt_percent(stock.near_wkl_pct),
                )
            )

        widths = [max(len(str(row[index])) for row in rows) for index in range(len(headers))]
        formatted_rows = []
        for row_index, row in enumerate(rows):
            formatted_rows.append(" | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))
            if row_index == 0:
                formatted_rows.append("-+-".join("-" * width for width in widths))
        return "\n".join(formatted_rows)

    def _fmt_currency(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value:.2f}"

    def _fmt_percent(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value * 100:.2f}%"
