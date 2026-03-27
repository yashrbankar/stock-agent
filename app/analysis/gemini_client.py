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
        if not self.clients:
            raise RuntimeError("No Gemini API key is configured")

        payload = {
            "symbol": stock.symbol,
            "company_name": stock.company_name,
            "price": _fmt(stock.price),
            "fifty_two_week_low": _fmt(stock.fifty_two_week_low),
            "near_wkl_pct": _fmt(stock.near_wkl_pct),
            "pe": _fmt(stock.pe),
            "pb": _fmt(stock.pb),
            "debt": _fmt(stock.debt_to_equity),
            "debt_to_equity": _fmt(stock.debt_to_equity),
            "per_change_30d": _fmt_pct(stock.thirty_day_change),
            "market_cap": _fmt(stock.market_cap),
        }
        system_instruction = load_prompt("system_prompt")
        user_prompt = render_prompt("analysis_prompt", payload)
        prompts = [
            user_prompt,
            (
                f"{user_prompt}\n\n"
                "The stock symbol and company have already been provided above. "
                "Do not ask for them again. Return the JSON object now."
            ),
        ]

        last_result: AnalysisResult | None = None
        for prompt in prompts:
            text = self._generate_text(
                prompt=prompt,
                system_instruction=system_instruction,
            )
            parsed = _parse_json_block(text)
            result = AnalysisResult(
                symbol=stock.symbol,
                company_name=stock.company_name,
                reason=parsed.get("reason", "No reason returned."),
                risks=_coerce_list(parsed.get("risks")),
                opportunity=parsed.get("opportunity", "No opportunity returned."),
                verdict=parsed.get("verdict", "WATCHLIST"),
                raw_text=text,
            )
            last_result = result
            if _is_analysis_usable(result):
                return result

            logger.warning("Gemini returned a low-quality analysis for %s; retrying once.", stock.symbol)

        assert last_result is not None
        return last_result

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
