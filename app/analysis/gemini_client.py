import json
import logging

from google import genai
from google.genai import types

from app.analysis.prompt_loader import load_prompt, render_prompt
from app.config import get_settings
from app.data.models import AnalysisResult, StockSnapshot


logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None

    def analyze(self, stock: StockSnapshot) -> AnalysisResult:
        if not self.client:
            raise RuntimeError("GEMINI_API_KEY is not configured")

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

        response = self.client.models.generate_content(
            model=self.settings.gemini_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = response.text or ""
        parsed = _parse_json_block(text)
        return AnalysisResult(
            symbol=stock.symbol,
            company_name=stock.company_name,
            reason=parsed.get("reason", "No reason returned."),
            risks=_coerce_list(parsed.get("risks")),
            opportunity=parsed.get("opportunity", "No opportunity returned."),
            verdict=parsed.get("verdict", "WATCHLIST"),
            raw_text=text,
        )

    def summarize(self, analyses: list[AnalysisResult]) -> str:
        if not self.client:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        system_instruction = load_prompt("system_prompt")
        summary_prompt = render_prompt(
            "summary_prompt",
            {"analysis_blob": json.dumps([item.model_dump() for item in analyses], indent=2)},
        )
        response = self.client.models.generate_content(
            model=self.settings.gemini_model,
            contents=summary_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        return response.text or "No summary generated."


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
