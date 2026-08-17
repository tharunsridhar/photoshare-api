"""Settings shared by every environment. development.py / production.py each
import * from here and override what needs to differ.

Everything security- or connectivity-sensitive comes from the environment
with no fallback - the same principle the FastAPI port used (pydantic-
settings with required fields there; os.environ[...] here, which raises
KeyError just as loudly if it's missing)."""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
# The FastAPI port used one JWT_SECRET for login tokens AND the email-
# verification/password-reset tokens. Kept as its own setting (rather than
# reusing SECRET_KEY) so rotating one doesn't silently invalidate the other.
JWT_SECRET = os.environ["JWT_SECRET"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    # domain apps
    "apps.accounts",
    "apps.posts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Postgres only - the whole point of this port is production parity, same as
# the FastAPI side. DATABASE_URL is required, no sqlite fallback.
DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "600")),
        conn_health_checks=True,
    )
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.PhotoShareJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# Access tokens only - the FastAPI port's JWTStrategy is a single stateless
# bearer token with a lifetime, no refresh-token concept, so there's nothing
# here to mirror from SimpleJWT's ROTATE_REFRESH_TOKENS/blacklist machinery.
JWT_LIFETIME_SECONDS = int(os.environ.get("JWT_LIFETIME_SECONDS", "3600"))
VERIFY_TOKEN_LIFETIME_SECONDS = int(os.environ.get("VERIFY_TOKEN_LIFETIME_SECONDS", "3600"))
RESET_TOKEN_LIFETIME_SECONDS = int(os.environ.get("RESET_TOKEN_LIFETIME_SECONDS", "3600"))

# --- media (ImageKit) ---
IMAGEKIT_PRIVATE_KEY = os.environ["IMAGEKIT_PRIVATE_KEY"]
IMAGEKIT_PUBLIC_KEY = os.environ["IMAGEKIT_PUBLIC_KEY"]
IMAGEKIT_URL = os.environ["IMAGEKIT_URL"]

# --- redis (cache-aside on /feed and /posts/{id}, celery broker + backend) ---
# DB 0 for the cache, DB 1 for celery - same split as the FastAPI port, so a
# FLUSHDB on one doesn't wipe the other.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
FEED_CACHE_TTL_SECONDS = int(os.environ.get("FEED_CACHE_TTL_SECONDS", "30"))
POST_CACHE_TTL_SECONDS = int(os.environ.get("POST_CACHE_TTL_SECONDS", "60"))

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
