from datetime import timedelta
from ipaddress import ip_network

import pytest
from axes.helpers import get_client_ip_address, get_cool_off
from axes.models import AccessAttempt
from django.contrib.sessions.models import Session
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.accounts.services import login_user as start_session

pytestmark = pytest.mark.django_db
PASSWORD = "Test-only!Authentication-8349"


@pytest.fixture
def login_user(user_model):
    return user_model.objects.create_user("login_employee", password=PASSWORD)


def post_login(client, username="login_employee", password=PASSWORD, **headers):
    return client.post(reverse("accounts:login"), {"username": username, "password": password}, **headers)


def test_login_rotates_session_and_post_logout_removes_authentication(client, login_user):
    session = client.session
    session["before_login"] = True
    session.save()
    old_key = session.session_key
    response = post_login(client)
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(login_user.pk)
    assert client.session.session_key != old_key
    assert not Session.objects.filter(session_key=old_key).exists()
    assert AuditLog.objects.filter(action="LOGIN", actor=login_user).count() == 1

    assert client.get(reverse("accounts:logout")).status_code == 405
    response = client.post(reverse("accounts:logout"))
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session
    assert AuditLog.objects.filter(action="LOGOUT", actor=login_user).count() == 1


def test_login_rejects_external_next_url(client, login_user):
    response = client.post(reverse("accounts:login"), {
        "username": login_user.username, "password": PASSWORD, "next": "https://evil.example/",
    })
    assert response.status_code == 302
    assert response.url == reverse("accounts:home")


def test_inactive_user_cannot_login(client, login_user):
    login_user.is_active = False
    login_user.save(update_fields=["is_active"])
    assert post_login(client).status_code == 200
    assert "_auth_user_id" not in client.session


def test_lockout_after_five_failures_including_correct_password(client, login_user, settings):
    assert settings.AXES_FAILURE_LIMIT == 5
    assert settings.AXES_LOCKOUT_PARAMETERS == [["username", "ip_address"]]
    assert get_cool_off() == timedelta(minutes=15)
    for attempt in range(5):
        response = post_login(client, password="wrong-password", REMOTE_ADDR="192.0.2.10")
        assert response.status_code == (429 if attempt == 4 else 200)
    assert b"15 minutes" in response.content
    assert post_login(client, REMOTE_ADDR="192.0.2.10").status_code == 429
    assert "_auth_user_id" not in client.session
    assert not AuditLog.objects.filter(action="LOGIN").exists()


def test_lockout_is_keyed_on_username_and_ip_combination(client, login_user, user_model):
    for attempt in range(5):
        post_login(client, password="wrong-password", REMOTE_ADDR="192.0.2.10")
    assert post_login(client, REMOTE_ADDR="192.0.2.11").status_code == 302
    client.post(reverse("accounts:logout"))
    second = user_model.objects.create_user("second_employee", password=PASSWORD)
    assert post_login(client, username=second.username, REMOTE_ADDR="192.0.2.10").status_code == 302


def test_cooldown_expires_without_sleep_and_blocked_attempt_does_not_extend_it(client, login_user):
    for attempt in range(5):
        post_login(client, password="wrong-password")
    previous_time = AccessAttempt.objects.get(username=login_user.username).attempt_time
    assert post_login(client).status_code == 429
    assert AccessAttempt.objects.get(username=login_user.username).attempt_time == previous_time
    AccessAttempt.objects.filter(username=login_user.username).update(
        attempt_time=timezone.now() - timedelta(minutes=16),
    )
    assert post_login(client).status_code == 302


def test_success_resets_failures_for_this_pair(client, login_user):
    post_login(client, password="wrong-password")
    assert AccessAttempt.objects.filter(username=login_user.username).exists()
    assert post_login(client).status_code == 302
    assert not AccessAttempt.objects.filter(username=login_user.username).exists()


def test_spoofed_forwarded_headers_cannot_bypass_lockout(client, login_user):
    for attempt in range(5):
        response = post_login(
            client, password="wrong-password", REMOTE_ADDR="192.0.2.10",
            HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt + 1}",
            HTTP_X_REAL_IP=f"198.51.100.{attempt + 1}",
        )
    assert response.status_code == 429
    assert AccessAttempt.objects.get(username=login_user.username).ip_address == "192.0.2.10"


def test_user_agent_changes_do_not_change_lockout_key_or_store_passwords(client, login_user):
    wrong_password = "Test-only!Do-not-store-this-password"
    for attempt in range(5):
        response = post_login(client, password=wrong_password, HTTP_USER_AGENT=f"client-{attempt}")
    assert response.status_code == 429
    assert AccessAttempt.objects.filter(username=login_user.username).count() == 5
    assert all(wrong_password not in entry.post_data for entry in AccessAttempt.objects.all())


@pytest.mark.parametrize("peer,header,expected", [
    ("10.0.0.5", "198.51.100.7", "198.51.100.7"),
    ("192.0.2.5", "198.51.100.7", "192.0.2.5"),
    ("10.0.0.5", "198.51.100.7, 198.51.100.8", "10.0.0.5"),
    ("10.0.0.5", "not-an-ip", "10.0.0.5"),
    ("10.0.0.5", "", "10.0.0.5"),
    ("2001:db8::5", "2001:db8:1::7", "2001:db8:1::7"),
    ("invalid", "198.51.100.7", None),
])
def test_safe_single_header_proxy_ip_resolution(settings, peer, header, expected):
    settings.TRUSTED_PROXY_NETWORKS = (ip_network("10.0.0.0/24"), ip_network("2001:db8::/64"))
    request = RequestFactory().get("/", REMOTE_ADDR=peer, HTTP_X_REAL_IP=header)
    assert get_client_ip_address(request) == expected


def test_login_and_logout_enforce_csrf_and_base_supplies_htmx_header(login_user):
    client = Client(enforce_csrf_checks=True)
    assert post_login(client).status_code == 403
    response = client.get(reverse("accounts:login"))
    assert b"hx-headers=" in response.content
    assert b"X-CSRFToken" in response.content
    token = response.context["csrf_token"]
    response = post_login(client, HTTP_X_CSRFTOKEN=str(token))
    assert response.status_code == 302
    assert client.post(reverse("accounts:logout")).status_code == 403
    token = client.get(reverse("accounts:home")).context["csrf_token"]
    assert client.post(reverse("accounts:logout"), HTTP_X_CSRFTOKEN=str(token)).status_code == 302


def test_login_audit_failure_leaves_no_authenticated_database_session(client, login_user, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr("apps.accounts.services.log_activity", fail)
    with pytest.raises(RuntimeError):
        post_login(client)
    assert not AuditLog.objects.exists()
    assert all("_auth_user_id" not in session.get_decoded() for session in Session.objects.all())


def test_login_service_rechecks_active_state_under_lock(login_user):
    request = RequestFactory().post(reverse("accounts:login"))
    request.session = SessionStore()
    login_user.is_active = False
    login_user.save(update_fields=["is_active"])
    with pytest.raises(PermissionDenied):
        start_session(request=request, user=login_user)
    assert not AuditLog.objects.exists()


def test_logout_audit_failure_rolls_back_database_session_deletion(client, login_user, monkeypatch):
    client.force_login(login_user)
    key = client.session.session_key
    def fail(**kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr("apps.accounts.services.log_activity", fail)
    with pytest.raises(RuntimeError):
        client.post(reverse("accounts:logout"))
    assert Session.objects.filter(session_key=key).exists()
    assert not AuditLog.objects.exists()
