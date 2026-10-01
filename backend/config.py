"""Environment/local configuration and the single source of scoring policy."""
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
import toml

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _secrets(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        values = toml.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, toml.TomlDecodeError):
        # Parse exceptions can contain credentials: log only the configuration stage.
        logger.warning("AI configuration could not be read (source=streamlit_secrets)")
        return {}
    return {name: value for name, value in values.items() if isinstance(value, str)}


def _configuration_sources(project_root: Path, user_home: Path):
    try:
        local_env = dotenv_values(project_root / ".env", encoding="utf-8-sig", interpolate=False)
    except (OSError, UnicodeError):
        logger.warning("AI configuration could not be read (source=dotenv)")
        local_env = {}
    return (os.environ, _secrets(project_root / ".streamlit" / "secrets.toml"),
            _secrets(user_home / ".streamlit" / "secrets.toml"), local_env)

CV_ONLY_WEIGHTS = {"content": .30, "experience": .125, "projects": .125, "skills": .20,
                   "structure": .15, "education": .10}
JOB_MATCH_WEIGHTS = {"hard_skills": .35, "experience": .20, "projects": .15,
                     "education": .10, "role": .10, "other": .10}
QUALITY_POINTS = {"unknown": 0, "insufficient": 15, "weak": 35, "limited": 52,
                  "adequate": 70, "strong": 82, "exceptional": 92}
MATCH_POINTS = {"missing": 0, "partial": 50, "matched": 100}
PREFERRED_REQUIREMENT_WEIGHT = .5
SCORING_VERSION = "2.0"


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-2.5-flash"
    timeout_ms: int = 30_000
    max_document_chars: int = 100_000

    @classmethod
    def from_env(cls, *, project_root: Path | None = None, user_home: Path | None = None):
        sources = _configuration_sources(project_root or PROJECT_ROOT, user_home or Path.home())

        def value(names, default=""):
            for source in sources:
                for name in names:
                    if name in source and isinstance(source[name], str):
                        return source[name].strip()
            return default

        key = value(("GEMINI_API_KEY", "GOOGLE_API_KEY"))
        if key.casefold() in {"-", "your-key", "your-api-key", "replace-me"}:
            key = ""
        return cls(gemini_api_key=key,
                   gemini_model=value(("GEMINI_MODEL",), "gemini-2.5-flash")
                   or "gemini-2.5-flash")
