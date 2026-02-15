import logging
import os
import re
from functools import lru_cache
from typing import Protocol

try:
    from better_profanity import profanity
except ModuleNotFoundError:  # pragma: no cover
    profanity = None

_ALLOWLIST_ENV_VAR = "HUSHLINE_CONTENT_FILTER_ALLOWLIST"
_logger = logging.getLogger(__name__)


class _ProfanityEngine(Protocol):
    def contains_profanity(self, text: str) -> bool: ...


def _allowlist() -> set[str]:
    value = os.getenv(_ALLOWLIST_ENV_VAR, "")
    return {item.strip().casefold() for item in value.split(",") if item.strip()}


def _strip_allowlisted_terms(text: str, allowlist: set[str]) -> str:
    sanitized = text
    for term in sorted(allowlist, key=len, reverse=True):
        sanitized = re.sub(rf"\b{re.escape(term)}\b", " ", sanitized, flags=re.IGNORECASE)
    return sanitized


@lru_cache(maxsize=1)
def _log_missing_library_once() -> None:
    _logger.warning(
        "better-profanity is not installed; content safety checks are temporarily disabled."
    )


@lru_cache(maxsize=1)
def _profanity_engine() -> _ProfanityEngine | None:
    if profanity is None:
        _log_missing_library_once()
        return None
    # Load the package-provided local wordlist once.
    profanity.load_censor_words()
    return profanity


def contains_disallowed_text(text: str | None) -> bool:
    if not text:
        return False

    candidate = text.casefold()
    allowlist = _allowlist()
    if allowlist:
        candidate = _strip_allowlisted_terms(candidate, allowlist)

    engine = _profanity_engine()
    if engine is None:
        return False
    return bool(engine.contains_profanity(candidate))
