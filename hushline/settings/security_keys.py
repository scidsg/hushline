import time
from http import HTTPStatus
from typing import Any, Mapping

import pyotp
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import validate_csrf
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import (
    WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY,
    authentication_required,
)
from hushline.db import db
from hushline.model import User, WebAuthnCredential
from hushline.settings.forms import SecurityKeyAuthorizationForm

ENROLLMENT_AUTHORIZATION_TTL_SECONDS = 300


def _active_credentials(user: User) -> list[WebAuthnCredential]:
    return [
        credential for credential in user.webauthn_credentials if credential.disabled_at is None
    ]


def _current_user() -> User:
    user = db.session.get(User, session["user_id"])
    if user is None:
        abort(401)
    return user


def _authorize_enrollment(user: User) -> None:
    session[WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY] = {
        "authorized_at": int(time.time()),
        "session_id": user.session_id,
        "user_id": user.id,
    }


def _clear_enrollment_authorization() -> None:
    session.pop(WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY, None)


def _has_recent_enrollment_authorization(user: User) -> bool:
    authorization = session.get(WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY)
    if not isinstance(authorization, Mapping):
        return False
    authorized_at = authorization.get("authorized_at")
    if not isinstance(authorized_at, int) or isinstance(authorized_at, bool):
        return False
    return (
        authorization.get("user_id") == user.id
        and authorization.get("session_id") == user.session_id
        and 0 <= int(time.time()) - authorized_at <= ENROLLMENT_AUTHORIZATION_TTL_SECONDS
    )


def _json_payload() -> Mapping[str, Any] | None:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, Mapping) else None


def _credential_name(payload: Mapping[str, Any]) -> str | None:
    name = payload.get("name")
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name or len(name) > WebAuthnCredential.MAX_NAME_LENGTH:
        return None
    return name


def _json_error(message: str, status: HTTPStatus) -> tuple[Response, int]:
    return jsonify({"error": message}), status.value


def _validate_json_csrf() -> str | None:
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return None

    token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    try:
        validate_csrf(token)
    except ValidationError:
        return "Invalid CSRF token."
    return None


def register_security_key_routes(bp: Blueprint) -> None:
    @bp.route("/security-keys")
    @authentication_required
    def security_keys() -> str:
        user = _current_user()
        authorized = _has_recent_enrollment_authorization(user)
        if not authorized:
            _clear_enrollment_authorization()
        return render_template(
            "settings/security_keys.html",
            authorization_form=SecurityKeyAuthorizationForm(),
            enrollment_authorized=authorized,
            credentials=_active_credentials(user),
            max_credentials=int(current_app.config["WEBAUTHN_MAX_CREDENTIALS_PER_USER"]),
            user=user,
        )

    @bp.route("/security-keys/authorize", methods=["POST"])
    @authentication_required
    def authorize_security_key() -> Response:
        user = _current_user()
        form = SecurityKeyAuthorizationForm()
        form_is_valid = form.validate_on_submit()
        if not form_is_valid and form.errors.get("csrf_token"):
            _clear_enrollment_authorization()
            abort(HTTPStatus.BAD_REQUEST)

        if form_is_valid:
            code = form.verification_code.data or ""
            totp_secret = user.totp_secret
            factor_is_valid = totp_secret is None or pyotp.TOTP(totp_secret).verify(
                code,
                valid_window=1,
            )
            if user.check_password(form.password.data) and factor_is_valid:
                _authorize_enrollment(user)
                return redirect(url_for(".security_keys"))

        _clear_enrollment_authorization()
        flash("⛔️ Current password or 2FA code is incorrect.")
        return redirect(url_for(".security_keys"))

    @bp.route("/security-keys/registration/options", methods=["POST"])
    @authentication_required
    def security_key_registration_options() -> tuple[Response, int] | Response:
        from hushline.webauthn import (
            WebAuthnCeremonyService,
            WebAuthnConfigurationError,
            WebAuthnRateLimitError,
            WebAuthnServiceError,
            current_webauthn_session_binding,
        )

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return _json_error(csrf_error, HTTPStatus.BAD_REQUEST)

        user = _current_user()
        if not _has_recent_enrollment_authorization(user):
            _clear_enrollment_authorization()
            return _json_error(
                "Reload this page, then confirm your password and existing 2FA method again.",
                HTTPStatus.FORBIDDEN,
            )

        payload = _json_payload()
        name = _credential_name(payload) if payload is not None else None
        if name is None:
            return _json_error("Enter a label for this security key.", HTTPStatus.BAD_REQUEST)
        if len(_active_credentials(user)) >= int(
            current_app.config["WEBAUTHN_MAX_CREDENTIALS_PER_USER"]
        ):
            return _json_error("The security key limit has been reached.", HTTPStatus.CONFLICT)

        try:
            options = WebAuthnCeremonyService.begin_registration(
                user=user,
                username=user.primary_username.username,
                display_name=user.primary_username.display_name,
                session_binding=current_webauthn_session_binding(),
            )
        except WebAuthnRateLimitError:
            return _json_error(
                "Too many enrollment attempts. Please wait and try again.",
                HTTPStatus.TOO_MANY_REQUESTS,
            )
        except WebAuthnConfigurationError:
            return _json_error(
                "Security key enrollment is temporarily unavailable.",
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except WebAuthnServiceError:
            return _json_error("Enrollment could not be started.", HTTPStatus.BAD_REQUEST)

        response = jsonify(options)
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.route("/security-keys/registration/verify", methods=["POST"])
    @authentication_required
    def verify_security_key_registration() -> tuple[Response, int] | Response:
        from hushline.webauthn import (
            WebAuthnCeremonyService,
            WebAuthnServiceError,
            current_webauthn_session_binding,
        )

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return _json_error(csrf_error, HTTPStatus.BAD_REQUEST)

        user = _current_user()
        if not _has_recent_enrollment_authorization(user):
            _clear_enrollment_authorization()
            return _json_error(
                "Reload this page, then confirm your password and existing 2FA method again.",
                HTTPStatus.FORBIDDEN,
            )

        payload = _json_payload()
        name = _credential_name(payload) if payload is not None else None
        credential_response = payload.get("credential") if payload is not None else None
        if name is None or not isinstance(credential_response, Mapping):
            _clear_enrollment_authorization()
            return _json_error("Enrollment response is invalid.", HTTPStatus.BAD_REQUEST)

        try:
            WebAuthnCeremonyService.finish_registration(
                user=user,
                session_binding=current_webauthn_session_binding(),
                response=credential_response,
                name=name,
            )
        except WebAuthnServiceError:
            return _json_error(
                "The security key could not be verified. No key was added.",
                HTTPStatus.BAD_REQUEST,
            )
        finally:
            _clear_enrollment_authorization()

        response = jsonify(
            {"message": "Security key added. Keep a backup key in a separate safe place."}
        )
        response.status_code = HTTPStatus.CREATED
        response.headers["Cache-Control"] = "no-store"
        return response
