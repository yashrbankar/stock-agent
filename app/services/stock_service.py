import logging
from html import escape

from app.analysis.gemini_client import GeminiAnalyzer
from app.config import get_settings
from app.data.fundamentals import FundamentalsClient
from app.data.models import AnalysisResult, PipelineRunResult, StockSnapshot
from app.data.nse_client import NSEClient
from app.filters.rules import filter_candidates
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
            return self._last_run.near_low_stocks

        candidates = self._load_candidates()
        near_low_stocks = filter_candidates(candidates)
        near_low_stocks = self._enrich_stocks_with_pe(near_low_stocks)
        return self._select_report_stocks(near_low_stocks)

    def run_pipeline(self, notify: bool = True) -> PipelineRunResult:
        logger.info(
            "Running stock pipeline with near_52_week_low_pct=%s and top_n=%s",
            self.settings.near_52_week_low_pct,
            self.settings.segment_top_n,
        )
        market_news: str | None = None
        try:
            market_news = self.analyzer.analyze_market_news()
        except Exception as exc:
            logger.exception("Failed to fetch market news")

        candidates = self._load_candidates()
        near_low_stocks = filter_candidates(candidates)
        enriched_stocks = self._enrich_stocks_with_pe(near_low_stocks)
        final_stocks = self._select_report_stocks(enriched_stocks)

        if not final_stocks:
            logger.info("No stocks found at default 5% near low. Trying 10%.")
            near_low_stocks = filter_candidates(candidates, override_pct=10.0)
            enriched_stocks = self._enrich_stocks_with_pe(near_low_stocks)
            final_stocks = self._select_report_stocks(enriched_stocks)

        near_low_stocks = final_stocks

        analyses: list = []
        gemini_failed = False
        gemini_failure_reason = ""
        
        if near_low_stocks:
            try:
                for batch in _chunked(near_low_stocks, self.settings.gemini_batch_size):
                    analyses.extend(self.analyzer.analyze_batch(batch))
            except Exception as exc:
                gemini_failed = True
                gemini_failure_reason = _format_user_friendly_error(exc)
                logger.exception(
                    "Gemini analysis failed. Falling back to near-low stock list only."
                )
        analyses = self._select_report_analyses(analyses)

        result = PipelineRunResult(
            scanned_count=len(candidates),
            near_low_stocks=near_low_stocks,
            analyses=analyses,
            market_news=market_news,
            gemini_failed=gemini_failed,
            gemini_failure_reason=gemini_failure_reason,
        )
        self._last_run = result

        report = self._build_report(result)
        html_report = self._build_html_report(result)
        if notify:
            self.email_notifier.send(
                "Stocks Near 52-Week Low",
                report,
                html_body=html_report,
            )
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
            "Stocks Near 52-Week Low",
            "=" * 72,
            "",
            "Scanned Universe",
            "-" * 72,
            f"Universe: {self.settings.nse_universe_label}",
            f"Stocks scanned: {result.scanned_count}",
            (
                f"Final stocks shown: {len(result.near_low_stocks)} "
                f"(within 52-week low threshold (up to 10%), "
                f"NSE P/E between 0 and 25, top {self.settings.segment_top_n} per segment by lowest P/E)"
            ),
            "",
        ]

        if result.market_news:
            lines.extend(
                [
                    "Market Hot Topics & News",
                    "-" * 72,
                    result.market_news,
                    "",
                ]
            )

        lines.extend(
            [
                "Stocks By Segment",
                "-" * 72,
                self._render_segmented_stock_list(result.near_low_stocks),
                "",
                "Fundamental Breakdown By Segment",
                "-" * 72,
            ]
        )

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
            lines.extend(self._render_segmented_analysis_sections(result.analyses))

        return "\n".join(lines)

    def _build_html_report(self, result: PipelineRunResult) -> str:
        stock_sections = []
        for segment_name, segment_stocks in self._group_stocks_by_segment(result.near_low_stocks).items():
            rows = "".join(
                [
                    (
                        "<tr>"
                        f"<td>{escape(stock.symbol)}</td>"
                        f"<td>{escape(stock.company_name)}</td>"
                        f"<td>{escape(self._fmt_number(stock.pe_ratio))}</td>"
                        f"<td>{escape(self._fmt_currency(stock.price))}</td>"
                        f"<td>{escape(self._fmt_percent(stock.near_wkl_pct))}</td>"
                        "</tr>"
                    )
                    for stock in segment_stocks
                ]
            )
            stock_sections.append(
                (
                    f"<section class='segment'>"
                    f"<h3>{escape(segment_name)}</h3>"
                    "<table>"
                    "<thead><tr><th>Symbol</th><th>Company</th><th>P/E</th><th>Price</th>"
                    "<th>Near 52W Low</th></tr></thead>"
                    f"<tbody>{rows}</tbody>"
                    "</table>"
                    "</section>"
                )
            )

        analysis_sections = []
        for segment_name, segment_analyses in self._group_analyses_by_segment(result.analyses).items():
            cards = "".join([self._render_html_analysis_card(analysis) for analysis in segment_analyses])
            analysis_sections.append(
                f"<section class='segment'><h3>{escape(segment_name)}</h3>{cards}</section>"
            )

        gemini_status = ""
        if result.gemini_failed:
            gemini_status = (
                "<section class='status warning'>"
                "<h2>Gemini Status</h2>"
                "<p>Gemini analysis failed in this run.</p>"
                f"<p><strong>Reason:</strong> {escape(result.gemini_failure_reason)}</p>"
                "</section>"
            )

        if not analysis_sections:
            analysis_sections.append("<p class='empty'>No Gemini analyses were produced for this run.</p>")

        rule_text = (
            f"Within 52-week low threshold (up to 10%), "
            f"NSE P/E between 0 and 25, top {self.settings.segment_top_n} by lowest P/E"
        )
        stock_sections_html = "".join(stock_sections)
        if not stock_sections_html:
            stock_sections_html = "<p class='empty'>No stocks in this section.</p>"
        analysis_sections_html = "".join(analysis_sections)

        market_news_html = ""
        if result.market_news:
            clean_news = escape(result.market_news).replace("#", "").replace("*", "")
            market_news_html = (
                 "<section class='segment'>"
                 "<h2>Market Hot Topics & News</h2>"
                 f"<div class='analysis-card'><pre style='white-space: pre-wrap; font-family: inherit; margin: 0;'>{clean_news}</pre></div>"
                 "</section>"
            )

        return (
            "<!DOCTYPE html>"
            "<html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<style>"
            "body{margin:0;padding:24px;background:#f4f1ea;color:#1f2937;"
            "font-family:Arial,sans-serif;line-height:1.5;}"
            ".wrap{max-width:1080px;margin:0 auto;background:#fffdf8;border:1px solid #e5dccf;"
            "border-radius:16px;padding:28px;}"
            "h1{margin:0 0 8px;font-size:28px;color:#111827;}"
            "h2{margin:28px 0 12px;font-size:18px;color:#7c2d12;}"
            "h3{margin:0 0 12px;font-size:16px;color:#92400e;}"
            ".meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;"
            "margin:20px 0;}"
            ".meta-card{background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:14px;}"
            ".meta-card .label{display:block;font-size:12px;color:#9a3412;text-transform:uppercase;"
            "letter-spacing:.04em;margin-bottom:6px;}"
            ".meta-card .value{font-size:18px;font-weight:700;color:#111827;}"
            ".segment{margin:20px 0 28px;}"
            "table{width:100%;border-collapse:collapse;background:#fff;}"
            "th,td{padding:10px 12px;border-bottom:1px solid #f1e7da;text-align:left;vertical-align:top;}"
            "th{background:#fff7ed;color:#7c2d12;font-size:12px;text-transform:uppercase;letter-spacing:.04em;}"
            ".analysis-card{border:1px solid #e5dccf;border-radius:14px;padding:16px;margin:14px 0;background:#fff;}"
            ".analysis-card h4{margin:0 0 10px;font-size:18px;color:#111827;}"
            ".field{margin:8px 0;}"
            ".field-label{font-weight:700;color:#92400e;}"
            "ul{margin:8px 0 0 20px;padding:0;}"
            ".status.warning{background:#fff7ed;border:1px solid #fdba74;border-radius:12px;padding:16px;}"
            ".empty{color:#6b7280;}"
            "</style></head><body>"
            "<div class='wrap'>"
            "<h1>Stocks Near 52-Week Low</h1>"
            "<div class='meta'>"
            f"{self._render_meta_card('Universe', self.settings.nse_universe_label)}"
            f"{self._render_meta_card('Stocks Scanned', str(result.scanned_count))}"
            f"{self._render_meta_card('Final Stocks Shown', str(len(result.near_low_stocks)))}"
            f"{self._render_meta_card('Rule', rule_text)}"
            "</div>"
            f"{market_news_html}"
            "<h2>Stocks By Segment</h2>"
            f"{stock_sections_html}"
            "<h2>Fundamental Breakdown By Segment</h2>"
            f"{gemini_status}"
            f"{analysis_sections_html}"
            "</div></body></html>"
        )

    def _render_segmented_stock_list(self, stocks: list[StockSnapshot]) -> str:
        if not stocks:
            return "No stocks in this section."

        lines: list[str] = []
        for segment_name, segment_stocks in self._group_stocks_by_segment(stocks).items():
            lines.extend(
                [
                    segment_name,
                    "-" * 32,
                ]
            )
            for stock in segment_stocks:
                lines.append(
                    f"- {stock.symbol}: {stock.company_name} | "
                    f"P/E {self._fmt_number(stock.pe_ratio)} | "
                    f"Price {self._fmt_currency(stock.price)} | "
                    f"Near low {self._fmt_percent(stock.near_wkl_pct)}"
                )
            lines.append("")
        return "\n".join(lines)

    def _render_analysis_section(self, analysis: AnalysisResult) -> list[str]:
        key_points = (
            ", ".join(analysis.key_points) if analysis.key_points else "No extra points noted."
        )
        risks = ", ".join(analysis.risks) if analysis.risks else "None noted."
        return [
            f"{analysis.symbol} - {analysis.company_name}",
            f"P/E: {self._fmt_number(analysis.pe_ratio)}",
            f"Business: {analysis.business_summary}",
            f"Valuation: {analysis.valuation_view}",
            f"Profit And Quality: {analysis.profitability_view}",
            f"Shareholding: {analysis.shareholding_view}",
            f"Key Points: {key_points}",
            f"Risks: {risks}",
            "",
        ]

    def _render_html_analysis_card(self, analysis: AnalysisResult) -> str:
        key_points = "".join(
            [f"<li>{escape(point)}</li>" for point in analysis.key_points]
        ) or "<li>No extra points noted.</li>"
        risks = "".join([f"<li>{escape(risk)}</li>" for risk in analysis.risks]) or "<li>None noted.</li>"
        return (
            "<article class='analysis-card'>"
            f"<h4>{escape(analysis.symbol)} - {escape(analysis.company_name)}</h4>"
            f"<div class='field'><span class='field-label'>P/E:</span> {escape(self._fmt_number(analysis.pe_ratio))}</div>"
            f"<div class='field'><span class='field-label'>Business:</span> {escape(analysis.business_summary)}</div>"
            f"<div class='field'><span class='field-label'>Valuation:</span> {escape(analysis.valuation_view)}</div>"
            f"<div class='field'><span class='field-label'>Profit And Quality:</span> {escape(analysis.profitability_view)}</div>"
            f"<div class='field'><span class='field-label'>Shareholding:</span> {escape(analysis.shareholding_view)}</div>"
            f"<div class='field'><span class='field-label'>Key Points:</span><ul>{key_points}</ul></div>"
            f"<div class='field'><span class='field-label'>Risks:</span><ul>{risks}</ul></div>"
            "</article>"
        )

    def _render_segmented_analysis_sections(self, analyses: list[AnalysisResult]) -> list[str]:
        if not analyses:
            return ["No Gemini analyses were produced for this run."]

        lines: list[str] = []
        for segment_name, segment_analyses in self._group_analyses_by_segment(analyses).items():
            lines.extend(
                [
                    segment_name,
                    "-" * 32,
                ]
            )
            for analysis in segment_analyses:
                lines.extend(self._render_analysis_section(analysis))
        return lines

    def _enrich_stocks_with_pe(self, stocks: list[StockSnapshot]) -> list[StockSnapshot]:
        if not stocks:
            return []
        pe_by_symbol = self.nse_client.fetch_pe_ratios([stock.symbol for stock in stocks])
        return [
            stock.model_copy(update={"pe_ratio": pe_by_symbol.get(stock.symbol)})
            for stock in stocks
        ]

    def _select_report_stocks(self, stocks: list[StockSnapshot]) -> list[StockSnapshot]:
        selected: list[StockSnapshot] = []
        for segment_name, segment_stocks in self._group_stocks_by_segment(stocks).items():
            positive_pe_stocks = [
                stock
                for stock in segment_stocks
                if stock.pe_ratio is not None and 0 < stock.pe_ratio <= 25
            ]
            positive_pe_stocks.sort(
                key=lambda stock: (
                    stock.pe_ratio if stock.pe_ratio is not None else 999999.0,
                    stock.near_wkl_pct if stock.near_wkl_pct is not None else 999999.0,
                )
            )
            selected.extend(positive_pe_stocks[: self.settings.segment_top_n])
        return selected

    def _select_report_analyses(self, analyses: list[AnalysisResult]) -> list[AnalysisResult]:
        selected: list[AnalysisResult] = []
        for segment_name, segment_analyses in self._group_analyses_by_segment(analyses).items():
            positive_pe_analyses = [
                analysis
                for analysis in segment_analyses
                if analysis.pe_ratio is not None and 0 < analysis.pe_ratio <= 25
            ]
            positive_pe_analyses.sort(
                key=lambda analysis: analysis.pe_ratio
                if analysis.pe_ratio is not None
                else 999999.0
            )
            selected.extend(positive_pe_analyses[: self.settings.segment_top_n])
        return selected

    def _group_stocks_by_segment(self, stocks: list[StockSnapshot]) -> dict[str, list[StockSnapshot]]:
        grouped: dict[str, list[StockSnapshot]] = {}
        for stock in stocks:
            grouped.setdefault(stock.segment, []).append(stock)
        return _order_grouped_segments(grouped, self.settings.nse_index_names)

    def _group_analyses_by_segment(
        self,
        analyses: list[AnalysisResult],
    ) -> dict[str, list[AnalysisResult]]:
        grouped: dict[str, list[AnalysisResult]] = {}
        for analysis in analyses:
            grouped.setdefault(analysis.segment, []).append(analysis)
        return _order_grouped_segments(grouped, self.settings.nse_index_names)

    def _fmt_currency(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value:.2f}"

    def _fmt_number(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value:.2f}"

    def _fmt_percent(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value * 100:.2f}%"

    def _render_meta_card(self, label: str, value: str) -> str:
        return (
            "<div class='meta-card'>"
            f"<span class='label'>{escape(label)}</span>"
            f"<span class='value'>{escape(value)}</span>"
            "</div>"
        )


def _chunked(items: list[StockSnapshot], chunk_size: int) -> list[list[StockSnapshot]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _order_grouped_segments(grouped: dict[str, list], ordered_segments: list[str]) -> dict[str, list]:
    ordered: dict[str, list] = {}
    for segment_name in ordered_segments:
        if segment_name in grouped:
            ordered[segment_name] = grouped[segment_name]
    for segment_name, items in grouped.items():
        if segment_name not in ordered:
            ordered[segment_name] = items
    return ordered


def _format_user_friendly_error(error: Exception) -> str:
    message = str(error).upper()
    if "RESOURCE_EXHAUSTED" in message or "429" in message or "QUOTA" in message:
        return "Gemini quota is exhausted right now. Stock analysis was skipped for this run."
    return "Gemini analysis is unavailable right now. Stock analysis was skipped for this run."
