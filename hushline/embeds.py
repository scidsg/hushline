import html
import ipaddress
import time
from dataclasses import dataclass
from hashlib import sha256
from hmac import new as hmac_new

from flask import current_app, request

from hushline.external_urls import canonical_external_url
from hushline.model import Username

EMBED_ABUSE_COUNTER_EVENT = "embed_form_abuse_counter"
EMBED_SUBMISSION_ATTEMPT_COUNTER = "embed_form_submission_attempt_total"
EMBED_SUBMISSION_ACCEPTED_COUNTER = "embed_form_submission_accepted_total"
EMBED_SUBMISSION_REJECTED_COUNTER = "embed_form_submission_rejected_total"
EMBED_SUBMISSION_RATE_LIMITED_COUNTER = "embed_form_submission_rate_limited_total"
EMBED_IFRAME_SANDBOX = (
    "allow-forms allow-popups allow-scripts allow-top-navigation-by-user-activation"
)
EMBED_IFRAME_HEIGHT = 700
EMBED_IFRAME_MAX_WIDTH = 720
_EMBED_RATE_LIMIT_EXTENSION_KEY = "hushline_embed_rate_limits"


@dataclass(frozen=True)
class EmbedRateLimitResult:
    limited: bool
    limited_scopes: tuple[str, ...]
    profile_hash: str
    source_bucket_hash: str


def embed_profile_url(username: Username) -> str:
    return canonical_external_url("embed_profile", username=username.username)


def embed_iframe_snippet(username: Username) -> str:
    src = html.escape(embed_profile_url(username), quote=True)
    title = html.escape(
        f"Send a secure Hush Line message to {username.display_name or username.username}"
    )
    return (
        f'<iframe src="{src}" '
        f'title="{title}" '
        f'sandbox="{EMBED_IFRAME_SANDBOX}" '
        'referrerpolicy="no-referrer" '
        'width="100%" '
        f'height="{EMBED_IFRAME_HEIGHT}" '
        f'style="width:100%;max-width:{EMBED_IFRAME_MAX_WIDTH}px;'
        f'height:{EMBED_IFRAME_HEIGHT}px;border:0;"></iframe>'
    )


def _embed_hmac(value: str) -> str:
    secret = (
        current_app.config.get("SECRET_KEY")
        or current_app.config.get("SESSION_FERNET_KEY")
        or current_app.config.get("ENCRYPTION_KEY")
        or ""
    )
    return hmac_new(str(secret).encode("utf-8"), value.encode("utf-8"), sha256).hexdigest()


def embed_profile_hash(username: Username) -> str:
    return _embed_hmac(f"profile:{username.id}:{username.username}")


def embed_source_bucket_hash() -> str:
    source_addr = request.remote_addr or "unknown"
    try:
        parsed_addr = ipaddress.ip_address(source_addr)
    except ValueError:
        source_bucket = "unknown"
    else:
        prefix = 24 if isinstance(parsed_addr, ipaddress.IPv4Address) else 64
        source_bucket = str(ipaddress.ip_network(f"{parsed_addr}/{prefix}", strict=False))
    return _embed_hmac(f"source:{source_bucket}")


def check_embed_rate_limit(username: Username) -> EmbedRateLimitResult:
    window_seconds = int(current_app.config.get("EMBED_RATE_LIMIT_WINDOW_SECONDS", 600))
    limits = {
        "profile": int(current_app.config.get("EMBED_RATE_LIMIT_PROFILE_MAX", 30)),
        "source": int(current_app.config.get("EMBED_RATE_LIMIT_SOURCE_MAX", 10)),
        "deployment": int(current_app.config.get("EMBED_RATE_LIMIT_DEPLOYMENT_MAX", 200)),
    }
    now = time.time()
    cutoff = now - window_seconds
    profile_hash = embed_profile_hash(username)
    source_bucket_hash = embed_source_bucket_hash()
    state: dict[str, list[float]] = current_app.extensions.setdefault(
        _EMBED_RATE_LIMIT_EXTENSION_KEY,
        {},
    )
    buckets = {
        "profile": f"profile:{profile_hash}",
        "source": f"source:{source_bucket_hash}",
        "deployment": "deployment",
    }

    for key, timestamps in list(state.items()):
        retained_timestamps = [timestamp for timestamp in timestamps if timestamp >= cutoff]
        if retained_timestamps:
            state[key] = retained_timestamps
        else:
            del state[key]

    limited_scopes: list[str] = []
    for scope, key in buckets.items():
        timestamps = state.get(key, [])
        if limits[scope] > 0 and len(timestamps) >= limits[scope]:
            limited_scopes.append(scope)

    if not limited_scopes:
        for key in buckets.values():
            state.setdefault(key, []).append(now)

    return EmbedRateLimitResult(
        limited=bool(limited_scopes),
        limited_scopes=tuple(limited_scopes),
        profile_hash=profile_hash,
        source_bucket_hash=source_bucket_hash,
    )


def emit_embed_abuse_counter(
    counter_name: str,
    *,
    profile_hash: str,
    source_bucket_hash: str,
    reason: str | None = None,
    limited_scopes: tuple[str, ...] = (),
) -> None:
    extra = {
        "event": EMBED_ABUSE_COUNTER_EVENT,
        "counter_name": counter_name,
        "count": 1,
        "profile_hash": profile_hash,
        "source_bucket_hash": source_bucket_hash,
    }
    if reason is not None:
        extra["reason"] = reason
    if limited_scopes:
        extra["limited_scopes"] = ",".join(limited_scopes)

    current_app.logger.info("Embed form abuse counter", extra=extra)
