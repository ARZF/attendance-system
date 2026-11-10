import json
import os
import subprocess
import sys

import pytest
from django.db import connection
from django.utils import timezone


def import_settings(module, overrides=None):
    environment = os.environ.copy()
    environment.update(
        DJANGO_SECRET_KEY="test-only-settings-key-not-a-production-secret",
        DJANGO_ALLOWED_HOSTS="attendance.example.com",
        POSTGRES_DB="attendance_settings_test",
        POSTGRES_USER="settings_test_user",
        POSTGRES_PASSWORD="test-only-settings-password",
    )
    for name, value in (overrides or {}).items():
        if value is None:
            environment.pop(name, None)
        else:
            environment[name] = value
    code = (
        "import importlib, json; "
        f"s = importlib.import_module('config.settings.{module}'); "
        "print(json.dumps({name: getattr(s, name) for name in "
        "['DEBUG', 'ALLOWED_HOSTS', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', "
        "'SESSION_COOKIE_HTTPONLY', 'CSRF_COOKIE_HTTPONLY', 'SECURE_SSL_REDIRECT', "
        "'SECURE_PROXY_SSL_HEADER', 'USE_X_FORWARDED_HOST', 'ENVIRONMENT']}))"
    )
    return subprocess.run(
        [sys.executable, "-c", code], env=environment, capture_output=True, text=True
    )


def test_production_security_defaults():
    result = import_settings("production", {"DJANGO_DEBUG": "True"})
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["DEBUG"] is False
    assert values["ALLOWED_HOSTS"] == ["attendance.example.com"]
    for name in [
        "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY",
        "CSRF_COOKIE_HTTPONLY", "SECURE_SSL_REDIRECT",
    ]:
        assert values[name] is True
    assert values["ENVIRONMENT"] == "production"
    assert values["SECURE_PROXY_SSL_HEADER"] is None
    assert values["USE_X_FORWARDED_HOST"] is False


@pytest.mark.parametrize(
    "name", ["DJANGO_SECRET_KEY", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
)
def test_production_requires_nonempty_secrets_and_database_configuration(name):
    result = import_settings("production", {name: ""})
    assert result.returncode != 0
    assert name in result.stderr


@pytest.mark.parametrize("hosts", ["", "*"])
def test_production_requires_explicit_allowed_hosts(hosts):
    result = import_settings("production", {"DJANGO_ALLOWED_HOSTS": hosts})
    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_development_allows_local_http():
    result = import_settings("development")
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["DEBUG"] is True
    assert values["ENVIRONMENT"] == "development"
    assert values["SESSION_COOKIE_SECURE"] is False
    assert values["CSRF_COOKIE_SECURE"] is False
    assert values["SECURE_SSL_REDIRECT"] is False
    assert "localhost" in values["ALLOWED_HOSTS"]


@pytest.mark.parametrize("cidrs", ["not-a-network", "0.0.0.0/0", "::/0"])
def test_proxy_configuration_rejects_invalid_or_universal_trust(cidrs):
    result = import_settings("production", {"DJANGO_TRUSTED_PROXY_CIDRS": cidrs})
    assert result.returncode != 0
    assert "DJANGO_TRUSTED_PROXY_CIDRS" in result.stderr


def test_timezone_and_custom_user_settings(settings):
    assert settings.USE_TZ is True
    assert settings.TIME_ZONE == "Asia/Tehran"
    assert str(timezone.get_default_timezone()) == "Asia/Tehran"
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.ENVIRONMENT == "test"
    assert settings.AUTH_PASSWORD_VALIDATORS


@pytest.mark.django_db
def test_database_is_postgresql_17_with_utc_storage():
    assert connection.vendor == "postgresql"
    assert connection.pg_version // 10000 == 17
    with connection.cursor() as cursor:
        cursor.execute("SHOW TIME ZONE")
        assert cursor.fetchone()[0] == "UTC"


@pytest.mark.django_db
def test_initial_migration_uses_custom_user_instead_of_auth_user():
    tables = connection.introspection.table_names()
    assert "accounts_user" in tables
    assert "auth_user" not in tables
