from pathlib import Path

from app.config import get_settings


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "N/A"


def load_prompt(name: str) -> str:
    prompts_dir: Path = get_settings().prompts_dir
    prompt_path = prompts_dir / f"{name}.txt"
    return prompt_path.read_text(encoding="utf-8")


def render_prompt(name: str, data: dict) -> str:
    template = load_prompt(name)
    return template.format_map(SafeFormatDict(data))
