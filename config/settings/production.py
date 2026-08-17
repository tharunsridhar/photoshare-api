import os

from .base import *  # noqa: F403

DEBUG = False

# Required in production - no "*" fallback like development.py has.
ALLOWED_HOSTS = [h.strip() for h in os.environ["ALLOWED_HOSTS"].split(",") if h.strip()]
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]

SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "true").lower() == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
