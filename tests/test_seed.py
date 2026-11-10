from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db


def test_seed_creates_one_development_user_per_role(user_model, seed_passwords):
    output = StringIO()
    call_command("seed", stdout=output)

    assert user_model.objects.count() == 3
    for role, password in seed_passwords.items():
        user = user_model.objects.get(username=f"demo_{role.lower()}")
        assert user.role == role
        assert user.check_password(password)
        assert not user.is_staff and not user.is_superuser
        assert password not in output.getvalue()


def test_seed_never_changes_existing_users(user_model, seed_passwords, monkeypatch):
    call_command("seed", stdout=StringIO())
    user = user_model.objects.get(username="demo_employee")
    user.role = user_model.Role.GUARD
    user.is_staff = True
    user.is_active = False
    user.set_password("Test-only!Existing-8392")
    user.save()
    original = list(user_model.objects.order_by("pk").values())

    for role in seed_passwords:
        monkeypatch.delenv(f"SEED_{role}_PASSWORD")
    call_command("seed", stdout=StringIO())

    assert list(user_model.objects.order_by("pk").values()) == original


@pytest.mark.parametrize("environment", ["production", "base"])
def test_seed_is_refused_outside_development_and_test(
    user_model, settings, seed_passwords, environment
):
    settings.ENVIRONMENT = environment
    with pytest.raises(CommandError, match="development and test"):
        call_command("seed")
    assert not user_model.objects.exists()


def test_seed_is_allowed_in_development(user_model, settings, seed_passwords):
    settings.ENVIRONMENT = "development"
    call_command("seed", stdout=StringIO())
    assert user_model.objects.count() == 3


def test_seed_missing_password_rolls_back_all_users(user_model, seed_passwords, monkeypatch):
    monkeypatch.delenv("SEED_ADMIN_PASSWORD")
    with pytest.raises(CommandError, match="SEED_ADMIN_PASSWORD"):
        call_command("seed")
    assert not user_model.objects.exists()


def test_seed_validates_passwords_and_rolls_back(user_model, seed_passwords, monkeypatch):
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "123")
    with pytest.raises(CommandError, match="password"):
        call_command("seed")
    assert not user_model.objects.exists()
