from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.models import User
from apps.accounts.tokens import InvalidTokenError, decode_token


class PhotoShareJWTAuthentication(BaseAuthentication):
    """Reads the bearer token issued by LoginView - a single stateless HS256
    JWT with no refresh token, matching the FastAPI port's fastapi-users
    JWTStrategy rather than SimpleJWT's access/refresh pair."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(f"{self.keyword} "):
            return None
        token = header[len(self.keyword) + 1 :]
        try:
            payload = decode_token(token, scope="photoshare:access")
        except InvalidTokenError as exc:
            raise AuthenticationFailed("Invalid token") from exc
        user = User.objects.filter(id=payload.get("sub"), is_active=True).first()
        if user is None:
            raise AuthenticationFailed("Invalid token")
        return (user, token)

    def authenticate_header(self, request):
        # non-None here is what makes DRF respond 401 (not 403) on missing
        # or invalid credentials
        return self.keyword
