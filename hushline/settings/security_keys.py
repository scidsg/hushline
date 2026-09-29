import time
from datetime import UTC, datetime, timedelta
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
from sqlalchemy import or_
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import (
    RECOVERY_CODES_PENDING_ACK_SESSION_KEY,
    STRONG_AUTHENTICATION_SESSION_KEY,
    WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY,
    WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY,
    WEBAUTHN_SESSION_BINDING_KEY,
    authentication_required,
    record_strong_authentication,
    rotate_user_session_id,
)
from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    RecoveryCode,
    RecoveryCodeBatch,
    User,
    WebAuthnChallenge,
    WebAuthnCredential,
)
from hushline.recovery_codes import acknowledge_recovery_codes, generate_recovery_codes
from hushline.settings.forms import (
    MfaPolicyChangeForm,
    RecoveryCodeAcknowledgementForm,
    RecoveryCodeGenerationForm,
    SecurityKeyAuthorizationForm,
    SecurityKeyRemovalForm,
    SecurityKeyRenameForm,
    TotpRemovalForm,
)

ENROLLMENT_AUTHORIZATION_TTL_SECONDS = 300


def _active_credentials(user: User) -> list[WebAuthnCredential]:
    return [
        credential for credential in user.webauthn_credentials if credential.disabled_at is None
    ]


def _lock_user(user_id: int) -> User:
    return db.session.scalars(
        db.select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def _invalidate_webauthn_challenges(user_id: int, *, when: datetime) -> None:
    db.session.execute(
        db.update(WebAuthnChallenge)
        .where(
            WebAuthnChallenge.user_id == user_id,
            WebAuthnChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=when)
    )


def _invalidate_recovery_codes(user_id: int, *, when: datetime) -> None:
    db.session.execute(
        db.update(RecoveryCodeBatch)
        .where(
            RecoveryCodeBatch.user_id == user_id,
            RecoveryCodeBatch.invalidated_at.is_(None),
        )
        .values(invalidated_at=when)
    )


def _prune_revoked_credentials(user_id: int) -> None:
    retention_limit = int(current_app.config.get("WEBAUTHN_MAX_REVOKED_CREDENTIALS_PER_USER", 20))
    retention_days = int(current_app.config.get("WEBAUTHN_REVOKED_CREDENTIAL_RETENTION_DAYS", 30))
    retention_cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    retained_ids = (
        db.select(WebAuthnCredential.id)
        .where(
            WebAuthnCredential.user_id == user_id,
            WebAuthnCredential.disabled_at.is_not(None),
        )
        .order_by(WebAuthnCredential.disabled_at.desc(), WebAuthnCredential.id.desc())
        .limit(retention_limit)
    )
    db.session.execute(
        db.delete(WebAuthnCredential)
        .where(
            WebAuthnCredential.user_id == user_id,
            WebAuthnCredential.disabled_at.is_not(None),
            or_(
                WebAuthnCredential.disabled_at < retention_cutoff,
                WebAuthnCredential.id.not_in(retained_ids),
            ),
        )
        .execution_options(synchronize_session=False)
    )


def _rotate_after_factor_policy_change(user: User) -> None:
    prior_authentication = session.get(STRONG_AUTHENTICATION_SESSION_KEY)
    method = (
        prior_authentication.get("method")
        if isinstance(prior_authentication, Mapping)
        else "factor_policy_change"
    )
    rotate_user_session_id(user)
    db.session.commit()
    session["session_id"] = user.session_id
    record_strong_authentication(user=user, method=str(method))


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


def _set_password_confirmation(user: User) -> None:
    session[WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY] = {
        "confirmed_at": int(time.time()),
        "session_id": user.session_id,
        "user_id": user.id,
    }


def _clear_password_confirmation() -> None:
    session.pop(WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY, None)


def _has_recent_password_confirmation(user: User) -> bool:
    confirmation = session.get(WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY)
    if not isinstance(confirmation, Mapping):
        return False
    confirmed_at = confirmation.get("confirmed_at")
    if not isinstance(confirmed_at, int) or isinstance(confirmed_at, bool):
        return False
    return (
        confirmation.get("user_id") == user.id
        and confirmation.get("session_id") == user.session_id
        and 0 <= int(time.time()) - confirmed_at <= ENROLLMENT_AUTHORIZATION_TTL_SECONDS
    )


def _has_recent_strong_authentication(user: User) -> bool:
    authentication = session.get(STRONG_AUTHENTICATION_SESSION_KEY)
    if not isinstance(authentication, Mapping):
        return False
    authenticated_at = authentication.get("authenticated_at")
    if not isinstance(authenticated_at, int) or isinstance(authenticated_at, bool):
        return False
    return (
        authentication.get("user_id") == user.id
        and authentication.get("session_id") == user.session_id
        and 0 <= int(time.time()) - authenticated_at <= ENROLLMENT_AUTHORIZATION_TTL_SECONDS
    )


def _verify_totp_reauthentication(user: User, code: str) -> bool:
    secret = user.totp_secret
    if not secret or not code:
        return False
    now = datetime.now()
    failed_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(AuthenticationLog)
        .where(
            AuthenticationLog.user_id == user.id,
            AuthenticationLog.successful == db.false(),
            AuthenticationLog.timestamp > now - timedelta(seconds=30),
        )
    )
    if failed_count is not None and failed_count >= 5:  # noqa: PLR2004
        return False

    totp = pyotp.TOTP(secret)
    timecode = totp.timecode(now)
    last_success = db.session.scalars(
        db.select(AuthenticationLog)
        .where(AuthenticationLog.user_id == user.id, AuthenticationLog.successful == db.true())
        .order_by(AuthenticationLog.timestamp.desc())
        .limit(1)
    ).first()
    valid = bool(
        not (last_success and last_success.timecode == timecode and last_success.otp_code == code)
        and totp.verify(code, valid_window=1)
    )
    db.session.add(
        AuthenticationLog(
            user_id=user.id,
            successful=valid,
            otp_code=code if valid else None,
            timecode=timecode if valid else None,
        )
    )
    db.session.commit()
    return valid


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


def _usable_recovery_code_count(user: User) -> int:
    count = db.session.scalar(
        db.select(db.func.count())
        .select_from(RecoveryCode)
        .join(RecoveryCodeBatch)
        .where(
            RecoveryCodeBatch.user_id == user.id,
            RecoveryCodeBatch.acknowledged_at.is_not(None),
            RecoveryCodeBatch.invalidated_at.is_(None),
            RecoveryCode.consumed_at.is_(None),
        )
    )
    return int(count or 0)


def _render_security_keys(
    user: User,
    *,
    generated_codes: list[str] | None = None,
) -> str:
    authorized = _has_recent_enrollment_authorization(user)
    if not authorized:
        _clear_enrollment_authorization()
    password_confirmed = _has_recent_password_confirmation(user)
    if not password_confirmed:
        _clear_password_confirmation()
    credentials = _active_credentials(user)
    return render_template(
        "settings/security_keys.html",
        acknowledgement_form=RecoveryCodeAcknowledgementForm(),
        authorization_form=SecurityKeyAuthorizationForm(),
        enrollment_authorized=authorized,
        credentials=credentials,
        generated_codes=generated_codes,
        generation_form=RecoveryCodeGenerationForm(),
        has_recovery_factor=bool(credentials or user.totp_secret),
        mfa_policy_form=MfaPolicyChangeForm(),
        max_credentials=int(current_app.config["WEBAUTHN_MAX_CREDENTIALS_PER_USER"]),
        password_confirmed=password_confirmed,
        recovery_code_count=_usable_recovery_code_count(user),
        removal_form=SecurityKeyRemovalForm(),
        rename_form=SecurityKeyRenameForm(),
        totp_removal_form=TotpRemovalForm(),
        user=user,
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
    response = jsonify({"error": message})
    response.headers["Cache-Control"] = "no-store"
    return response, status.value


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
        return _render_security_keys(user)

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
            credentials = _active_credentials(user)
            password_is_valid = user.check_password(form.password.data)
            recent_strong_authentication = _has_recent_strong_authentication(user)
            factor_is_valid = bool(
                password_is_valid
                and not recent_strong_authentication
                and totp_secret
                and code
                and _verify_totp_reauthentication(user, code)
            )
            if password_is_valid and (
                factor_is_valid or recent_strong_authentication or not (totp_secret or credentials)
            ):
                if factor_is_valid:
                    record_strong_authentication(user=user, method="totp")
                _authorize_enrollment(user)
                _clear_password_confirmation()
                return redirect(url_for(".security_keys"))
            if password_is_valid and credentials and not code:
                _set_password_confirmation(user)
                flash("Use an enrolled security key to finish confirming your identity.")
                return redirect(url_for(".security_keys"))

        _clear_enrollment_authorization()
        _clear_password_confirmation()
        flash("⛔️ Current password or 2FA code is incorrect.")
        return redirect(url_for(".security_keys"))

    @bp.post("/security-keys/authorization/options")
    @authentication_required
    def security_key_authorization_options() -> tuple[Response, int] | Response:
        from hushline.webauthn import (
            WebAuthnCeremonyService,
            WebAuthnConfigurationError,
            WebAuthnPurpose,
            WebAuthnRateLimitError,
            WebAuthnServiceError,
            current_webauthn_session_binding,
        )

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return _json_error(csrf_error, HTTPStatus.BAD_REQUEST)
        user = _current_user()
        if not _has_recent_password_confirmation(user):
            _clear_password_confirmation()
            return _json_error("Confirm your current password again.", HTTPStatus.FORBIDDEN)
        try:
            options = WebAuthnCeremonyService.begin_authentication(
                user=user,
                session_binding=current_webauthn_session_binding(),
                purpose=WebAuthnPurpose.RECOVERY,
            )
        except WebAuthnRateLimitError:
            return _json_error(
                "Too many confirmation attempts. Please wait and try again.",
                HTTPStatus.TOO_MANY_REQUESTS,
            )
        except WebAuthnConfigurationError:
            return _json_error(
                "Security key confirmation is temporarily unavailable.",
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except WebAuthnServiceError:
            return _json_error("Confirmation could not be started.", HTTPStatus.BAD_REQUEST)
        response = jsonify(options)
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/security-keys/authorization/verify")
    @authentication_required
    def verify_security_key_authorization() -> tuple[Response, int] | Response:
        from hushline.webauthn import (
            WebAuthnCeremonyService,
            WebAuthnPurpose,
            WebAuthnServiceError,
            current_webauthn_session_binding,
        )

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return _json_error(csrf_error, HTTPStatus.BAD_REQUEST)
        user = _current_user()
        if not _has_recent_password_confirmation(user):
            _clear_password_confirmation()
            return _json_error("Confirm your current password again.", HTTPStatus.FORBIDDEN)
        payload = _json_payload()
        credential_response = payload.get("credential") if payload is not None else None
        if not isinstance(credential_response, Mapping):
            return _json_error("Security key response is invalid.", HTTPStatus.BAD_REQUEST)
        try:
            WebAuthnCeremonyService.finish_authentication(
                user=user,
                session_binding=current_webauthn_session_binding(),
                response=credential_response,
                purpose=WebAuthnPurpose.RECOVERY,
            )
        except WebAuthnServiceError:
            return _json_error("The security key could not be verified.", HTTPStatus.UNAUTHORIZED)

        _authorize_enrollment(user)
        record_strong_authentication(user=user, method="security_key")
        _clear_password_confirmation()
        session.pop(WEBAUTHN_SESSION_BINDING_KEY, None)
        response = jsonify({"redirect": url_for(".security_keys")})
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/security-keys/recovery-codes/generate")
    @authentication_required
    def generate_security_key_recovery_codes() -> Response | str:
        user = _current_user()
        form = RecoveryCodeGenerationForm()
        if not form.validate_on_submit():
            abort(HTTPStatus.BAD_REQUEST)
        if not _has_recent_enrollment_authorization(user):
            _clear_enrollment_authorization()
            flash("Confirm your identity again before generating recovery codes.")
            return redirect(url_for(".security_keys"))
        if not (_active_credentials(user) or user.totp_secret):
            _clear_enrollment_authorization()
            flash("Add a security key or authenticator app before generating recovery codes.")
            return redirect(url_for(".security_keys"))

        batch, codes = generate_recovery_codes(user)
        session[RECOVERY_CODES_PENDING_ACK_SESSION_KEY] = {
            "batch_id": batch.id,
            "session_id": user.session_id,
            "user_id": user.id,
        }
        _clear_enrollment_authorization()
        response = current_app.make_response(_render_security_keys(user, generated_codes=codes))
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/security-keys/recovery-codes/acknowledge")
    @authentication_required
    def acknowledge_security_key_recovery_codes() -> Response:
        user = _current_user()
        form = RecoveryCodeAcknowledgementForm()
        pending = session.get(RECOVERY_CODES_PENDING_ACK_SESSION_KEY)
        if not form.validate_on_submit() or not isinstance(pending, Mapping):
            abort(HTTPStatus.BAD_REQUEST)
        batch_id = pending.get("batch_id")
        if (
            not isinstance(batch_id, int)
            or isinstance(batch_id, bool)
            or pending.get("user_id") != user.id
            or pending.get("session_id") != user.session_id
            or not acknowledge_recovery_codes(user_id=user.id, batch_id=batch_id)
        ):
            db.session.rollback()
            session.pop(RECOVERY_CODES_PENDING_ACK_SESSION_KEY, None)
            abort(HTTPStatus.BAD_REQUEST)

        prior_authentication = session.get(STRONG_AUTHENTICATION_SESSION_KEY)
        method = (
            prior_authentication.get("method")
            if isinstance(prior_authentication, Mapping)
            else "recovery_policy_change"
        )
        rotate_user_session_id(user)
        db.session.commit()
        session["session_id"] = user.session_id
        session.pop(RECOVERY_CODES_PENDING_ACK_SESSION_KEY, None)
        record_strong_authentication(user=user, method=str(method))
        flash("Recovery codes are ready. Each code can be used once.", "success")
        return redirect(url_for(".security_keys"))

    @bp.post("/security-keys/remove")
    @authentication_required
    def remove_security_key() -> Response:
        user = _current_user()
        form = SecurityKeyRemovalForm()
        if not form.validate_on_submit():
            abort(HTTPStatus.BAD_REQUEST)
        if not _has_recent_enrollment_authorization(user):
            _clear_enrollment_authorization()
            flash("Confirm your identity again before removing a security key.")
            return redirect(url_for(".security_keys"))
        try:
            credential_id = int(form.credential_id.data)
        except (TypeError, ValueError):
            abort(HTTPStatus.BAD_REQUEST)
        user = _lock_user(user.id)
        credential = db.session.scalar(
            db.select(WebAuthnCredential).where(
                WebAuthnCredential.id == credential_id,
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.disabled_at.is_(None),
            )
        )
        if credential is None:
            abort(HTTPStatus.NOT_FOUND)
        other_credential_count = db.session.scalar(
            db.select(db.func.count())
            .select_from(WebAuthnCredential)
            .where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.id != credential.id,
                WebAuthnCredential.disabled_at.is_(None),
            )
        )
        if not (other_credential_count or user.totp_secret):
            db.session.rollback()
            flash("Add another security key or authenticator app before removing this key.")
            return redirect(url_for(".security_keys"))

        now = datetime.now(UTC)
        credential.disabled_at = now
        _invalidate_webauthn_challenges(user.id, when=now)
        _prune_revoked_credentials(user.id)
        _rotate_after_factor_policy_change(user)
        _clear_enrollment_authorization()
        session.pop(WEBAUTHN_SESSION_BINDING_KEY, None)
        flash("Security key removed. Other sessions have been signed out.", "success")
        return redirect(url_for(".security_keys"))

    @bp.post("/security-keys/rename")
    @authentication_required
    def rename_security_key() -> Response:
        user = _current_user()
        form = SecurityKeyRenameForm()
        if not form.validate_on_submit():
            abort(HTTPStatus.BAD_REQUEST)
        if not _has_recent_enrollment_authorization(user):
            _clear_enrollment_authorization()
            flash("Confirm your identity again before renaming a security key.")
            return redirect(url_for(".security_keys"))
        try:
            credential_id = int(form.credential_id.data)
        except (TypeError, ValueError):
            abort(HTTPStatus.BAD_REQUEST)
        name = (form.name.data or "").strip()
        if not name or len(name) > WebAuthnCredential.MAX_NAME_LENGTH:
            abort(HTTPStatus.BAD_REQUEST)
        credential = db.session.scalar(
            db.select(WebAuthnCredential)
            .where(
                WebAuthnCredential.id == credential_id,
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.disabled_at.is_(None),
            )
            .with_for_update()
        )
        if credential is None:
            abort(HTTPStatus.NOT_FOUND)
        credential.name = name
        db.session.commit()
        flash("Security key renamed.", "success")
        return redirect(url_for(".security_keys"))

    @bp.post("/security-keys/remove-totp")
    @authentication_required
    def remove_totp_factor() -> Response:
        user = _current_user()
        form = TotpRemovalForm()
        if not form.validate_on_submit():
            abort(HTTPStatus.BAD_REQUEST)
        if not _has_recent_enrollment_authorization(user):
            _clear_enrollment_authorization()
            flash("Confirm your identity again before removing your authenticator app.")
            return redirect(url_for(".security_keys"))
        user = _lock_user(user.id)
        active_credential_count = db.session.scalar(
            db.select(db.func.count())
            .select_from(WebAuthnCredential)
            .where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.disabled_at.is_(None),
            )
        )
        if not user.totp_secret:
            db.session.rollback()
            abort(HTTPStatus.NOT_FOUND)
        if not active_credential_count:
            db.session.rollback()
            flash("Add a security key before removing your only second factor.")
            return redirect(url_for(".security_keys"))
        user.totp_secret = None
        _rotate_after_factor_policy_change(user)
        _clear_enrollment_authorization()
        flash(
            "Authenticator app removed. Your security keys are still required at login, and "
            "other sessions have been signed out.",
            "success",
        )
        return redirect(url_for(".security_keys"))

    @bp.post("/security-keys/disable-mfa")
    @authentication_required
    def disable_mfa() -> Response:
        user = _current_user()
        form = MfaPolicyChangeForm()
        if not form.validate_on_submit():
            abort(HTTPStatus.BAD_REQUEST)
        if not _has_recent_enrollment_authorization(user):
            _clear_enrollment_authorization()
            flash("Confirm your identity again before disabling MFA.")
            return redirect(url_for(".security_keys"))

        user = _lock_user(user.id)
        now = datetime.now(UTC)
        db.session.execute(
            db.update(WebAuthnCredential)
            .where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.disabled_at.is_(None),
            )
            .values(disabled_at=now)
        )
        user.totp_secret = None
        _invalidate_recovery_codes(user.id, when=now)
        _invalidate_webauthn_challenges(user.id, when=now)
        _prune_revoked_credentials(user.id)
        _rotate_after_factor_policy_change(user)
        _clear_enrollment_authorization()
        session.pop(WEBAUTHN_SESSION_BINDING_KEY, None)
        flash(
            "MFA disabled. Security keys, authenticator codes, and recovery codes no longer "
            "protect this account. Other sessions have been signed out.",
            "success",
        )
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

        user = _lock_user(user.id)
        _rotate_after_factor_policy_change(user)

        response = jsonify(
            {"message": "Security key added. Keep a backup key in a separate safe place."}
        )
        response.status_code = HTTPStatus.CREATED
        response.headers["Cache-Control"] = "no-store"
        return response
