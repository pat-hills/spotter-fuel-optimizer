from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SECRET_KEY

DEBUG = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

if SECRET_KEY == "unsafe-development-key-change-me" or len(SECRET_KEY) < 40:
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY to a random value of at least 40 characters."
    )
