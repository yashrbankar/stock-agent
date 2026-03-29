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
        near_low_5_pct = select_near_low_stocks(
            candidates,
            max_threshold=self.settings.bucket_1_near_wkl_pct,
        )
        near_low_10_pct = select_near_low_stocks(
            candidates,
            min_threshold=self.settings.bucket_1_near_wkl_pct,
            max_threshold=self.settings.bucket_2_near_wkl_pct,
        )
        shortlist = near_low_5_pct + near_low_10_pct
        filtered = filter_candidates(shortlist)

        analyses: list = []
        summary = self._build_summary(candidates, shortlist, filtered, near_low_5_pct, near_low_10_pct)
        gemini_failed = False
        gemini_failure_reason = ""
        if filtered:
            try:
                analyses = []
                for batch in _chunked(filtered, self.settings.gemini_batch_size):
                    analyses.extend(self.analyzer.analyze_batch(batch))
                analysis_summary = self.analyzer.summarize(analyses) if analyses else "No qualifying stocks today."
                summary = f"{summary}\n\nFiltered stock summary\n{analysis_summary}"
            except Exception as exc:
                gemini_failed = True
                gemini_failure_reason = str(exc)
                summary = f"{summary}\n\nGemini analysis is not available right now."
                logger.exception("Gemini analysis failed. Falling back to near-low stock lists only.")

        result = PipelineRunResult(
            candidates=candidates,
            filtered=filtered,
            near_low_5_pct=near_low_5_pct,
            near_low_10_pct=near_low_10_pct,
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
            "=" * 72,
            "",
            "Snapshot",
            "-" * 72,
            f"Revision: {os.getenv('GITHUB_SHA', 'local')[:7]}",
            f"Universe: {self.settings.nse_index_name}",
            f"Candidates scanned: {len(result.candidates)}",
            f"Stocks within 10% of 52-week low: {len(result.near_low_5_pct) + len(result.near_low_10_pct)}",
            f"Best stocks after filters: {len(result.filtered)}",
            "",
            "Screen Rules",
            "-" * 72,
            "- Full universe is scanned",
            f"- Shortlist includes stocks within 0% to {self.settings.bucket_2_near_wkl_pct:.1f}% of 52-week low",
            f"- PE < {self.settings.filter_max_pe}",
            f"- PB < {self.settings.filter_max_pb}",
            f"- Debt/Equity < {self.settings.filter_max_debt_to_equity}",
            f"- 30-day change < {self.settings.filter_max_30d_change * 100:.1f}%",
            "",
            "Summary",
            "-" * 72,
            result.summary,
            "",
            f"Shortlist: Within {self.settings.bucket_1_near_wkl_pct:.1f}% of 52-week low",
            "-" * 72,
            self._render_stock_list(result.near_low_5_pct),
            "",
            (
                f"Shortlist: {self.settings.bucket_1_near_wkl_pct:.1f}% to "
                f"{self.settings.bucket_2_near_wkl_pct:.1f}% above 52-week low"
            ),
            "-" * 72,
            self._render_stock_list(result.near_low_10_pct),
            "",
            "Best Stocks After Filters",
            "-" * 72,
            self._render_stock_list(result.filtered, include_metrics=True),
            "",
            "Detailed Analyses",
            "-" * 72,
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

        if not result.analyses:
            lines.append("No Gemini analyses were produced for this run.")
        else:
            for index, analysis in enumerate(result.analyses, start=1):
                lines.extend(
                    [
                        f"{index}. {analysis.symbol} - {analysis.company_name}",
                        f"Verdict: {analysis.verdict}",
                        f"Why it is here: {analysis.reason}",
                        f"Opportunity: {analysis.opportunity or 'None noted'}",
                        f"Risks: {', '.join(analysis.risks) if analysis.risks else 'None listed'}",
                        "",
                    ]
                )

        return "\n".join(lines)

    def _render_stock_list(self, stocks: list[StockSnapshot], *, include_metrics: bool = False) -> str:
        if not stocks:
            return "No stocks in this section."

        lines: list[str] = []
        for stock in stocks:
            line = (
                f"- {stock.symbol}: {stock.company_name} | "
                f"Price {self._fmt_currency(stock.price)} | "
                f"Near low {self._fmt_percent(stock.near_wkl_pct)}"
            )
            if include_metrics:
                line += (
                    f" | PE {self._fmt_number(stock.pe)}"
                    f" | PB {self._fmt_number(stock.pb)}"
                    f" | Debt/Equity {self._fmt_number(stock.debt_to_equity)}"
                    f" | 30d {self._fmt_percent(stock.thirty_day_change)}"
                )
            lines.append(line)
        return "\n".join(lines)

    def _fmt_currency(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value:.2f}"

    def _fmt_percent(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value * 100:.2f}%"

    def _fmt_number(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value:.2f}"

    def _build_summary(
        self,
        candidates: list[StockSnapshot],
        shortlist: list[StockSnapshot],
        filtered: list[StockSnapshot],
        near_low_5_pct: list[StockSnapshot],
        near_low_10_pct: list[StockSnapshot],
    ) -> str:
        lines = [
            f"- Scanned {len(candidates)} stocks from {self.settings.nse_index_name}.",
            f"- Found {len(shortlist)} stocks within 10% of their 52-week low.",
            (
                f"- Bucket counts: <=5%: {len(near_low_5_pct)} | "
                f"5-10%: {len(near_low_10_pct)}"
            ),
            f"- Passed all filters: {len(filtered)}",
        ]
        if filtered:
            lines.append(f"- Best stocks today: {', '.join(stock.symbol for stock in filtered[:15])}")
        else:
            lines.append("- Best stocks today: None")
        return "\n".join(lines)


def _chunked(items: list[StockSnapshot], chunk_size: int) -> list[list[StockSnapshot]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]
