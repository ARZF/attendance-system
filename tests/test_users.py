import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db


def test_create_user_defaults_to_employee_and_hashes_password(user_model):
    user = user_model.objects.create_user("alice", password="test-only-password")

    assert user.role == user_model.Role.EMPLOYEE
    assert user.check_password("test-only-password")
    assert user.password != "test-only-password"
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.parametrize("role", ["EMPLOYEE", "GUARD", "ADMIN"])
def test_business_role_does_not_grant_staff_permissions(user_model, role):
    user = user_model.objects.create_user("alice", role=role)

    assert user.role == role
    assert not user.is_staff
    assert not user.is_superuser


def test_create_superuser_gets_admin_role(user_model):
    user = user_model.objects.create_superuser(
        "root", email="root@example.com", password="test-only-password"
    )

    assert user.role == user_model.Role.ADMIN
    assert user.is_staff
    assert user.is_superuser
    assert user.check_password("test-only-password")


def test_createsuperuser_command_gets_admin_role(user_model, monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "Test-only!Root-7294")
    call_command(
        "createsuperuser", username="root", email="", interactive=False, verbosity=0
    )

    user = user_model.objects.get(username="root")
    assert user.role == user_model.Role.ADMIN
    assert user.is_staff and user.is_superuser
    assert user.check_password("Test-only!Root-7294")


@pytest.mark.parametrize("role", ["EMPLOYEE", "GUARD", "INVALID"])
def test_superuser_rejects_non_admin_role(user_model, role):
    with pytest.raises(ValueError, match="ADMIN"):
        user_model.objects.create_superuser("root", role=role)
    assert not user_model.objects.exists()


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
def test_superuser_requires_django_permission_flags(user_model, flag):
    with pytest.raises(ValueError, match=flag):
        user_model.objects.create_superuser("root", **{flag: False})


def test_username_is_required(user_model):
    with pytest.raises(ValueError, match="username"):
        user_model.objects.create_user("")


def test_username_is_unique(user_model):
    user_model.objects.create_user("alice")
    with pytest.raises(IntegrityError), transaction.atomic():
        user_model.objects.create_user("alice")


def test_email_is_optional_and_non_unique(user_model):
    first = user_model.objects.create_user("alice", email="team@example.com")
    second = user_model.objects.create_user("bob", email="team@example.com")
    third = user_model.objects.create_user("charlie")

    assert first.email == second.email
    assert third.email == ""


def test_missing_password_is_unusable(user_model):
    user = user_model.objects.create_user("alice")
    assert not user.has_usable_password()


def test_database_rejects_invalid_role_even_on_queryset_update(user_model):
    user = user_model.objects.create_user("alice")
    with pytest.raises(IntegrityError), transaction.atomic():
        user_model.objects.filter(pk=user.pk).update(role="INVALID")
    user.refresh_from_db()
    assert user.role == user_model.Role.EMPLOYEE


def test_role_has_requested_headroom(user_model):
    assert user_model._meta.get_field("role").max_length == 16
