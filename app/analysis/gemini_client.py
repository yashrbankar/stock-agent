import json
import logging

from google import genai
from google.genai import errors, types

from app.analysis.prompt_loader import load_prompt, render_prompt
from app.config import get_settings
from app.data.models import AnalysisResult, StockSnapshot

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.clients = [genai.Client(api_key=key) for key in settings.gemini_api_keys]

    def analyze(self, stock: StockSnapshot) -> AnalysisResult:
        return self.analyze_batch([stock])[0]

    def analyze_batch(self, stocks: list[StockSnapshot]) -> list[AnalysisResult]:
        if not self.clients:
            raise RuntimeError("No Gemini API key is configured")
        if not stocks:
            return []
        if len(stocks) > self.settings.gemini_batch_size:
            raise ValueError(
                f"Batch size {len(stocks)} exceeds configured Gemini batch size "
                f"{self.settings.gemini_batch_size}"
            )

        system_instruction = load_prompt("system_prompt")
        user_prompt = render_prompt(
            "batch_analysis_prompt",
            {"stocks_blob": json.dumps([_stock_payload(stock) for stock in stocks], indent=2)},
        )
        prompts = [
            user_prompt,
            (
                f"{user_prompt}\n\n"
                "The stocks, symbols, and metrics have already been provided above. "
                "Do not ask for them again. Return only the JSON array now."
            ),
        ]

        last_results: list[AnalysisResult] | None = None
        for prompt in prompts:
            text = self._generate_text(
                prompt=prompt,
                system_instruction=system_instruction,
            )
            results = _parse_batch_results(text, stocks)
            last_results = results
            if len(results) == len(stocks) and all(
                _is_analysis_usable(result) for result in results
            ):
                return results

            logger.warning(
                "Gemini returned a low-quality batch analysis for %s stock(s); retrying once.",
                len(stocks),
            )

        assert last_results is not None
        return last_results

    def summarize(self, analyses: list[AnalysisResult]) -> str:
        if not analyses:
            return "No qualifying stocks today."

        watchlist = [item.symbol for item in analyses if item.verdict == "WATCHLIST"]
        buy = [item.symbol for item in analyses if item.verdict == "BUY"]
        avoid = [item.symbol for item in analyses if item.verdict == "AVOID"]

        takeaway = (
            f"{len(analyses)} stock(s) passed the quantitative screen. "
            f"BUY: {len(buy)}, WATCHLIST: {len(watchlist)}, AVOID: {len(avoid)}."
        )
        watchlist_line = ", ".join(buy + watchlist) if (buy or watchlist) else "None"
        avoid_line = ", ".join(avoid) if avoid else "None"

        return (
            f"{takeaway}\n\n"
            f"Top watchlist names: {watchlist_line}\n"
            f"Avoid for now: {avoid_line}"
        )

    def _generate_text(self, *, prompt: str, system_instruction: str) -> str:
        last_error: Exception | None = None

        for index, client in enumerate(self.clients, start=1):
            try:
                response = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                    ),
                )
                logger.info("Gemini request succeeded using API key #%s", index)
                return response.text or ""
            except errors.ClientError as exc:
                last_error = exc
                status = str(getattr(exc, "status", "")).upper()
                message = str(getattr(exc, "message", "")).upper()
                if status == "RESOURCE_EXHAUSTED" or "RESOURCE_EXHAUSTED" in message:
                    logger.warning("Gemini key #%s hit quota. Trying next key if available.", index)
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("No Gemini client is available")


def _parse_json_block(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        logger.warning("Gemini returned non-JSON output; falling back to text parsing.")
        return {"reason": stripped, "risks": [], "opportunity": "", "verdict": "WATCHLIST"}


def _parse_batch_results(text: str, stocks: list[StockSnapshot]) -> list[AnalysisResult]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        logger.warning("Gemini returned non-JSON batch output; using fallback results.")
        return [_fallback_analysis(stock, stripped) for stock in stocks]

    if not isinstance(parsed, list):
        logger.warning("Gemini batch output was not a JSON array; using fallback results.")
        return [_fallback_analysis(stock, stripped) for stock in stocks]

    items_by_symbol = {}
    for item in parsed:
        if isinstance(item, dict) and item.get("symbol"):
            items_by_symbol[str(item["symbol"]).upper()] = item

    results: list[AnalysisResult] = []
    for stock in stocks:
        item = items_by_symbol.get(stock.symbol.upper())
        if not item:
            results.append(_fallback_analysis(stock, stripped))
            continue
        results.append(
            AnalysisResult(
                symbol=stock.symbol,
                company_name=stock.company_name,
                reason=str(item.get("reason", "No reason returned.")),
                risks=_coerce_list(item.get("risks")),
                opportunity=str(item.get("opportunity", "No opportunity returned.")),
                verdict=str(item.get("verdict", "WATCHLIST")),
                raw_text=text,
            )
        )
    return results


def _coerce_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _stock_payload(stock: StockSnapshot) -> dict[str, str]:
    return {
        "symbol": stock.symbol,
        "company_name": stock.company_name,
        "industry": stock.industry or "N/A",
        "price": _fmt(stock.price),
        "fifty_two_week_low": _fmt(stock.fifty_two_week_low),
        "near_wkl_pct": _fmt_pct(stock.near_wkl_pct),
        "day_change": _fmt_pct(stock.day_change),
        "per_change_30d": _fmt_pct(stock.thirty_day_change),
        "per_change_365d": _fmt_pct(stock.one_year_change),
        "traded_value_cr": _fmt_cr(stock.traded_value),
        "traded_volume": _fmt(stock.traded_volume),
    }


def _fmt_cr(value: float | None) -> str:
    return "N/A" if value is None else f"{value / 10_000_000:.2f}"


def _fallback_analysis(stock: StockSnapshot, raw_text: str) -> AnalysisResult:
    return AnalysisResult(
        symbol=stock.symbol,
        company_name=stock.company_name,
        reason=raw_text or "No reason returned.",
        risks=[],
        opportunity="",
        verdict="WATCHLIST",
        raw_text=raw_text,
    )


def _is_analysis_usable(result: AnalysisResult) -> bool:
    bad_phrases = (
        "please provide the stock symbol",
        "please provide the company name",
        "which stock would you like",
        "i need the stock symbol",
    )
    content = " ".join([result.reason, result.opportunity, result.raw_text]).lower()
    if any(phrase in content for phrase in bad_phrases):
        return False
    if len(result.reason.strip()) < 25:
        return False
    return True
