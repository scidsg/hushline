import base64
import io

import pyotp
import qrcode
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import User
from hushline.routes import (
    TwoFactorForm,
)


def register_2fa_routes(bp: Blueprint) -> None:
    @bp.route("/toggle-2fa", methods=["POST"])
    @authentication_required
    def toggle_2fa() -> Response:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if user and user.totp_secret:
            return redirect(url_for(".disable_2fa"))

        return redirect(url_for(".enable_2fa"))

    @bp.route("/enable-2fa", methods=["GET", "POST"])
    @authentication_required
    def enable_2fa() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        form = TwoFactorForm()

        if form.validate_on_submit():
            temp_totp_secret = session.get("temp_totp_secret")
            verification_code = form.verification_code.data
            if (
                verification_code
                and temp_totp_secret
                and pyotp.TOTP(temp_totp_secret).verify(verification_code, valid_window=1)
                and user
            ):
                user.totp_secret = temp_totp_secret
                db.session.commit()
                session.pop("temp_totp_secret", None)
                flash("👍 2FA setup successful. Please log in again with 2FA.")
                return redirect(url_for("logout"))

            flash("⛔️ Invalid 2FA code. Please try again.")
            return redirect(url_for(".enable_2fa"))

        # Generate new 2FA secret and QR code
        temp_totp_secret = pyotp.random_base32()
        session["temp_totp_secret"] = temp_totp_secret
        session["is_setting_up_2fa"] = True
        if user:
            totp_uri = pyotp.totp.TOTP(temp_totp_secret).provisioning_uri(
                name=user.primary_username.username, issuer_name="HushLine"
            )
        img = qrcode.make(totp_uri)
        buffered = io.BytesIO()
        img.save(buffered)
        qr_code_img = "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()

        return render_template(
            "enable_2fa.html",
            form=form,
            qr_code_img=qr_code_img,
            text_code=temp_totp_secret,
            user=user,
        )

    @bp.route("/disable-2fa", methods=["POST"])
    @authentication_required
    def disable_2fa() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if user:
            user.totp_secret = None
        db.session.commit()
        flash("🔓 2FA has been disabled.")
        return redirect(url_for(".auth"))

    @bp.route("/confirm-disable-2fa")
    @authentication_required
    def confirm_disable_2fa() -> str:
        return render_template("confirm_disable_2fa.html")

    @bp.route("/verify-2fa-setup", methods=["POST"])
    @authentication_required
    def verify_2fa_setup() -> Response | str:
        user = db.session.get(User, session["user_id"])
        if not user:
            return redirect(url_for("login"))

        if not user.totp_secret:
            flash("⛔️ 2FA setup failed. Please try again.")
            return redirect(url_for(".enable_2fa"))

        verification_code = request.form["verification_code"]
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(verification_code, valid_window=1):
            flash("⛔️ Invalid 2FA code. Please try again.")
            return redirect(url_for(".enable_2fa"))

        flash("👍 2FA setup successful. Please log in again.")
        session.pop("is_setting_up_2fa", None)
        return redirect(url_for("logout"))
