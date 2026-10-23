
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from the project's root .env file.
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "unsafe-development-key-change-me",
)
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1",
    ).split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.fuel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "spotter"),
        "USER": os.getenv("POSTGRES_USER", "spotter"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "spotter"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {"connect_timeout": 5},
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("API_ANON_RATE", "60/min"),
    },
    "EXCEPTION_HANDLER": "apps.fuel.api.exceptions.api_exception_handler",
}

CACHE_URL = os.getenv("CACHE_URL", "")

if CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": CACHE_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "spotter-route-cache",
        }
    }

ROUTING_BASE_URL = os.getenv(
    "ROUTING_BASE_URL",
    "https://router.project-osrm.org",
)
ROUTING_TIMEOUT_SECONDS = float(
    os.getenv("ROUTING_TIMEOUT_SECONDS", "8")
)
ROUTING_CACHE_SECONDS = int(
    os.getenv("ROUTING_CACHE_SECONDS", "3600")
)

GEOCODING_TIMEOUT_SECONDS = float(
    os.getenv("GEOCODING_TIMEOUT_SECONDS", "5")
)
GEOCODING_USER_AGENT = os.getenv(
    "GEOCODING_USER_AGENT",
    "spotter-fuel-optimizer-assessment/1.0 "
    "(contact: developer@example.com)",
)

# Google Maps Platform configuration.
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_MAPS_TIMEOUT_SECONDS = float(
    os.getenv("GOOGLE_MAPS_TIMEOUT_SECONDS", "10")
)

MAX_STATION_DISTANCE_MILES = float(
    os.getenv("MAX_STATION_DISTANCE_MILES", "8")
)
MAX_ROUTE_STATIONS = int(
    os.getenv("MAX_ROUTE_STATIONS", "10000")
)
