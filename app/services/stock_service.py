import logging
import os

from app.analysis.gemini_client import GeminiAnalyzer
from app.data.fundamentals import FundamentalsClient
from app.data.models import PipelineRunResult, StockSnapshot
from app.data.nse_client import NSEClient
from app.filters.rules import filter_candidates
from app.notification.emailer import EmailNotifier
from app.notification.whatsapp import WhatsAppNotifier


logger = logging.getLogger(__name__)


class StockService:
    def __init__(self) -> None:
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
        analyses = [self.analyzer.analyze(stock) for stock in filtered]
        summary = self.analyzer.summarize(analyses) if analyses else "No qualifying stocks today."

        result = PipelineRunResult(
            candidates=candidates,
            filtered=filtered,
            analyses=analyses,
            summary=summary,
        )
        self._last_run = result

        if notify:
            report = self._build_report(result)
            self.email_notifier.send("Daily Stock Bot Report", report)
            self.whatsapp_notifier.send(report)

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
            f"Candidates scanned: {len(result.candidates)}",
            f"After filters: {len(result.filtered)}",
            "",
            "Executive Summary",
            result.summary,
            "",
            "Detailed Analyses",
        ]

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
