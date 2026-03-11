import urllib.parse

from flask import current_app, url_for


def normalize_public_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("PUBLIC_BASE_URL must use http or https")
    if not parsed.netloc:
        raise ValueError("PUBLIC_BASE_URL must include a host")
    if parsed.path not in {"", "/"}:
        raise ValueError("PUBLIC_BASE_URL must not include a path")
    if parsed.query or parsed.fragment:
        raise ValueError("PUBLIC_BASE_URL must not include query or fragment components")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def canonical_external_url(endpoint: str, **values: str) -> str:
    public_base_url = current_app.config.get("PUBLIC_BASE_URL")
    if public_base_url:
        relative_url = url_for(endpoint, _external=False, **values)
        return urllib.parse.urljoin(f"{public_base_url}/", relative_url.lstrip("/"))

    server_name = current_app.config.get("SERVER_NAME")
    if server_name:
        return url_for(
            endpoint,
            _external=True,
            _scheme=current_app.config["PREFERRED_URL_SCHEME"],
            **values,
        )

    if (
        current_app.config.get("TESTING")
        or current_app.config.get("DEBUG")
        or current_app.config.get("FLASK_ENV") == "development"
    ):
        current_app.logger.warning(
            "PUBLIC_BASE_URL and SERVER_NAME are unset; falling back to request-derived "
            "external URL generation in development/testing."
        )
        return url_for(
            endpoint,
            _external=True,
            _scheme=current_app.config["PREFERRED_URL_SCHEME"],
            **values,
        )

    raise RuntimeError(
        "Canonical external URL generation requires PUBLIC_BASE_URL "
        "or SERVER_NAME to be configured."
    )
