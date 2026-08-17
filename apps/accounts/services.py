"""Verification and password-reset flows. There's no mail service wired up
here - same gap the FastAPI port has (its on_after_request_verify /
on_after_forgot_password hooks just print the token) - so these return the
token directly to the caller rather than emailing it."""

from apps.accounts.models import User
from apps.accounts.tokens import InvalidTokenError, decode_token, make_reset_token, make_verify_token, password_fingerprint


def request_verify(user: User) -> str:
    token = make_verify_token(user)
    print(f"Verification requested for user {user.id}. Verification token: {token}")
    return token


def verify_token(token: str) -> User:
    payload = decode_token(token, scope="photoshare:verify")
    user = User.objects.filter(id=payload["sub"]).first()
    if user is None or password_fingerprint(user) != payload.get("pwd_fp"):
        raise InvalidTokenError("token no longer valid")
    user.is_verified = True
    user.save(update_fields=["is_verified"])
    return user


def forgot_password(user: User) -> str:
    token = make_reset_token(user)
    print(f"User {user.id} has forgotten password. Reset token: {token}")
    return token


def reset_password(token: str, new_password: str) -> User:
    payload = decode_token(token, scope="photoshare:reset")
    user = User.objects.filter(id=payload["sub"]).first()
    if user is None or password_fingerprint(user) != payload.get("pwd_fp"):
        raise InvalidTokenError("token no longer valid")
    user.set_password(new_password)
    user.save(update_fields=["password"])
    return user
