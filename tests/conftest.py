import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def user_model():
    return get_user_model()


@pytest.fixture
def actors(user_model):
    return {
        name: user_model.objects.create_user(name, role=role)
        for name, role in {
            "admin": "ADMIN",
            "guard": "GUARD",
            "other_guard": "GUARD",
            "employee": "EMPLOYEE",
            "other_employee": "EMPLOYEE",
        }.items()
    }


@pytest.fixture
def seed_passwords(monkeypatch):
    passwords = {
        "EMPLOYEE": "Test-only!River-employee-4829",
        "GUARD": "Test-only!Mountain-guard-5931",
        "ADMIN": "Test-only!Forest-admin-6042",
    }
    for role, password in passwords.items():
        monkeypatch.setenv(f"SEED_{role}_PASSWORD", password)
    return passwords
