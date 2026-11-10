from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

ENVIRONMENT = "production"

if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set DJANGO_ALLOWED_HOSTS to explicit production hostnames.")

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
