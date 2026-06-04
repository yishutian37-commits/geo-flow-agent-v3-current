from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import sys
from typing import Any, Mapping


PROMPT_ROOT = Path(__file__).resolve().parent


def _prompt_root_candidates() -> list[Path]:
    candidates = [PROMPT_ROOT]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "app" / "prompts")
    candidates.append(Path.cwd() / "app" / "prompts")
    return candidates


@lru_cache(maxsize=64)
def load_prompt_template(relative_path: str) -> str:
    """Load a prompt template from backend/app/prompts."""
    safe_path = Path(relative_path)
    if safe_path.is_absolute() or ".." in safe_path.parts:
        raise ValueError(f"Invalid prompt template path: {relative_path}")
    path = next((root / safe_path for root in _prompt_root_candidates() if (root / safe_path).exists()), None)
    if path is None:
        searched = ", ".join(str(root / safe_path) for root in _prompt_root_candidates())
        raise FileNotFoundError(f"Prompt template not found: {relative_path}; searched: {searched}")
    return path.read_text(encoding="utf-8")


def render_prompt_template(relative_path: str, variables: Mapping[str, Any]) -> str:
    """Render {{name}} placeholders without treating JSON braces as format tokens."""
    text = load_prompt_template(relative_path)
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", "" if value is None else str(value))
    return text
