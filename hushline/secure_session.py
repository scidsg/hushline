import json
from json import JSONDecodeError

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, Request, Response
from flask.sessions import SecureCookieSession, SessionInterface, SessionMixin


class AccessTrackingSecureCookieSession(SecureCookieSession):
    """Ensure key-only reads count as access for cache-vary/session semantics."""

    def __contains__(self, key: object) -> bool:
        self.accessed = True
        return super().__contains__(key)

    def __len__(self) -> int:
        self.accessed = True
        return super().__len__()


class EncryptedSessionInterface(SessionInterface):
    """
    Config:
    - SESSION_FERNET_KEY: string representing a Fernet key
    """

    session_class = AccessTrackingSecureCookieSession

    def _get_fernet(self, app: Flask) -> Fernet | None:
        if key := app.config.get("SESSION_FERNET_KEY"):
            return Fernet(key)
        return None

    def open_session(self, app: Flask, request: Request) -> SecureCookieSession | None:
        if not (fernet := self._get_fernet(app)):
            return None

        if not (val := request.cookies.get(self.get_cookie_name(app))):
            return self.session_class()

        max_age = int(app.permanent_session_lifetime.total_seconds())
        try:
            data = fernet.decrypt(val, ttl=max_age)
        except InvalidToken:
            return self.session_class()

        try:
            decoded = json.loads(data)
        except JSONDecodeError:
            return self.session_class()

        return self.session_class(decoded)

    def save_session(self, app: Flask, session: SessionMixin, response: Response) -> None:
        name = self.get_cookie_name(app)
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        secure = self.get_cookie_secure(app)
        partitioned = self.get_cookie_partitioned(app)
        samesite = self.get_cookie_samesite(app)
        httponly = self.get_cookie_httponly(app)

        # Add a "Vary: Cookie" header if the session was accessed at all.
        if session.accessed:
            response.vary.add("Cookie")

        # If the session is modified to be empty, remove the cookie.
        # If the session is empty, return without setting the cookie.
        if not session:
            if session.modified:
                response.delete_cookie(
                    name,
                    domain=domain,
                    path=path,
                    secure=secure,
                    partitioned=partitioned,
                    samesite=samesite,
                    httponly=httponly,
                )
                response.vary.add("Cookie")

            return

        if not self.should_set_cookie(app, session):
            return

        expires = self.get_expiration_time(app, session)
        if not (fernet := self._get_fernet(app)):
            raise RuntimeError("Fernet key not set")

        val = fernet.encrypt(json.dumps(dict(session)).encode("utf-8")).decode("utf-8")
        response.set_cookie(
            name,
            val,
            expires=expires,
            httponly=httponly,
            domain=domain,
            path=path,
            secure=secure,
            partitioned=partitioned,
            samesite=samesite,
        )
        response.vary.add("Cookie")
