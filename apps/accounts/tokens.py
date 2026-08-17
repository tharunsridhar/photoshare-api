"""JWT helpers for the three token kinds this app issues: login access
tokens, email-verification tokens, and password-reset tokens. All three are
single stateless HS256 JWTs signed with JWT_SECRET (mirroring the FastAPI
port's fastapi-users JWTStrategy, which also uses one secret for all three)
- distinguished by an `aud` (audience) claim so a verify token can't be
replayed as a reset token or vice versa.

Verify/reset tokens additionally bind to a fingerprint of the user's current
password hash: once the password actually changes (a reset uses it, or the
user changes their password some other way), any outstanding token for that
user is instantly worthless, not just single-use by convention.
"""

from datetime import UTC, datetime, timedelta

import jwt
from django.conf import settings


class InvalidTokenError(Exception):
    pass


def password_fingerprint(user) -> str:
    return user.password[-16:]


def _make_token(user, scope: str, lifetime_seconds: int, bind_password: bool = False) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "aud": scope,
        "iat": now,
        "exp": now + timedelta(seconds=lifetime_seconds),
    }
    if bind_password:
        payload["pwd_fp"] = password_fingerprint(user)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def make_access_token(user) -> str:
    return _make_token(user, "photoshare:access", settings.JWT_LIFETIME_SECONDS)


def make_verify_token(user) -> str:
    return _make_token(user, "photoshare:verify", settings.VERIFY_TOKEN_LIFETIME_SECONDS, bind_password=True)


def make_reset_token(user) -> str:
    return _make_token(user, "photoshare:reset", settings.RESET_TOKEN_LIFETIME_SECONDS, bind_password=True)


def decode_token(token: str, scope: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], audience=scope)
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
