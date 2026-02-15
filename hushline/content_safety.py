import os
import re
from hashlib import sha256
from functools import lru_cache

try:
    from better_profanity import profanity as better_profanity
except ModuleNotFoundError:  # pragma: no cover - covered in environments without dependency
    better_profanity = None

_ALLOWLIST_ENV_VAR = "HUSHLINE_CONTENT_FILTER_ALLOWLIST"
_HASHED_BLOCKLIST_ENV_VAR = "HUSHLINE_DISALLOWED_TEXT_SHA256"


def _allowlist() -> set[str]:
    value = os.getenv(_ALLOWLIST_ENV_VAR, "")
    return {item.strip().casefold() for item in value.split(",") if item.strip()}


def _strip_allowlisted_terms(text: str, allowlist: set[str]) -> str:
    sanitized = text
    for term in sorted(allowlist, key=len, reverse=True):
        sanitized = re.sub(rf"\b{re.escape(term)}\b", " ", sanitized, flags=re.IGNORECASE)
    return sanitized


@lru_cache(maxsize=1)
def _hashed_blocklist() -> set[str]:
    value = os.getenv(_HASHED_BLOCKLIST_ENV_VAR, "")
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _tokenize(text: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    return {token for token in normalized.split() if token}


def _contains_hashed_match(text: str) -> bool:
    hashes = _hashed_blocklist()
    if not hashes:
        return False

    for token in _tokenize(text):
        if sha256(token.encode("utf-8")).hexdigest() in hashes:
            return True
    return False


@lru_cache(maxsize=1)
def _profanity_engine() -> object | None:
    if better_profanity is None:
        return None
    # Load the package-provided local wordlist once.
    better_profanity.load_censor_words()
    return better_profanity


def contains_disallowed_text(text: str | None) -> bool:
    if not text:
        return False

    candidate = text.casefold()
    allowlist = _allowlist()
    if allowlist:
        candidate = _strip_allowlisted_terms(candidate, allowlist)

    engine = _profanity_engine()
    if engine is not None:
        return bool(engine.contains_profanity(candidate))
    return _contains_hashed_match(candidate)
