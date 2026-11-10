import pytest
from django.contrib import admin
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.accounts.models import User
from apps.attendance.models import GuardAssignment
from apps.attendance.services import assign_guard
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("name", ["employee", "guard", "admin"])
@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("page,allowed", [
    ("home", {"employee", "guard", "admin"}),
    ("employees", {"employee", "guard", "admin"}),
    ("assignments", {"admin"}),
    ("users", {"admin"}),
])
def test_page_role_matrix(client, actors, name, partial, page, allowed):
    client.force_login(actors[name])
    response = client.get(reverse(f"accounts:{page}"), HTTP_HX_REQUEST="true" if partial else "false")
    assert response.status_code == (200 if name in allowed else 403)


@pytest.mark.parametrize("page", ["home", "employees", "assignments", "users"])
def test_anonymous_page_access_redirects_to_login(client, page):
    response = client.get(reverse(f"accounts:{page}"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


def test_expired_session_partial_redirects_without_returning_private_html(client):
    response = client.get(reverse("accounts:assignments"), HTTP_HX_REQUEST="true")
    assert response.status_code == 401
    assert reverse("accounts:login") in response["HX-Redirect"]
    assert not response.content


def test_admin_staff_without_superuser_flags_can_view_but_not_edit_admin_models(client, actors):
    user = actors["admin"]
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client.force_login(user)
    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 200
    assert client.post(reverse("admin:accounts_user_add"), {}).status_code == 403


@pytest.mark.parametrize("partial", [False, True])
def test_employee_idor_and_guard_scope_return_404(client, actors, partial):
    url = reverse("accounts:employee_detail", args=[actors["employee"].pk])
    headers = {"HTTP_HX_REQUEST": "true" if partial else "false"}
    client.force_login(actors["other_employee"])
    assert client.get(url, **headers).status_code == 404
    client.force_login(actors["guard"])
    assert client.get(url, **headers).status_code == 404
    first = assign_guard(
        actor=actors["admin"], employee_id=actors["employee"].pk,
        guard_id=actors["guard"].pk, expected_assignment_id=None,
    )
    assert client.get(url, **headers).status_code == 200
    assign_guard(
        actor=actors["admin"], employee_id=actors["employee"].pk,
        guard_id=actors["other_guard"].pk, expected_assignment_id=first.pk,
    )
    assert client.get(url, **headers).status_code == 404
    client.force_login(actors["other_guard"])
    response = client.get(url, **headers)
    assert response.status_code == 200
    assert actors["guard"].username.encode() in response.content
    client.force_login(actors["admin"])
    assert client.get(url, **headers).status_code == 200


@pytest.mark.parametrize("name", ["employee", "guard"])
@pytest.mark.parametrize("partial", [False, True])
def test_assignment_post_and_role_change_cannot_be_called_by_other_roles(client, actors, name, partial):
    client.force_login(actors[name])
    headers = {"HTTP_HX_REQUEST": "true" if partial else "false"}
    response = client.post(reverse("accounts:assignments"), {
        "action": "assign", "employee_id": actors["employee"].pk,
        "guard_id": actors["guard"].pk,
    }, **headers)
    assert response.status_code == 403
    response = client.post(reverse("accounts:role_change", args=[actors["other_employee"].pk]), {
        "role": "ADMIN",
    }, **headers)
    assert response.status_code == 403
    assert not GuardAssignment.objects.exists()
    assert not AuditLog.objects.filter(action="ROLE_CHANGED").exists()


def test_htmx_assignment_post_requires_csrf_and_returns_authorized_partial(actors):
    client = Client(enforce_csrf_checks=True)
    client.force_login(actors["admin"])
    url = reverse("accounts:assignments")
    data = {"action": "assign", "employee_id": actors["employee"].pk, "guard_id": actors["guard"].pk}
    assert client.post(url, data, HTTP_HX_REQUEST="true").status_code == 403
    token = client.get(url).context["csrf_token"]
    response = client.post(url, data, HTTP_HX_REQUEST="true", HTTP_X_CSRFTOKEN=str(token))
    assert response.status_code == 200
    assert b"<!doctype html>" not in response.content.lower()
    assert GuardAssignment.objects.count() == 1


def test_admin_assignment_forms_validate_and_check_end_idor(client, actors):
    client.force_login(actors["admin"])
    url = reverse("accounts:assignments")
    assert client.post(url, {"action": "assign", "employee_id": "not-a-number"}).status_code == 200
    assert not GuardAssignment.objects.exists()
    client.post(url, {
        "action": "assign", "employee_id": actors["employee"].pk, "guard_id": actors["guard"].pk,
    })
    assignment = GuardAssignment.objects.get()
    response = client.post(url, {
        "action": "end", "employee_id": actors["other_employee"].pk,
        "assignment_id": assignment.pk,
    })
    assert response.status_code == 404
    assert GuardAssignment.objects.get().ended_at is None


def test_role_change_page_calls_audited_service(client, actors):
    client.force_login(actors["admin"])
    url = reverse("accounts:role_change", args=[actors["employee"].pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {"role": "GUARD"}).status_code == 302
    assert AuditLog.objects.get(action="ROLE_CHANGED").target_employee_id == actors["employee"].pk


@pytest.mark.parametrize("name", ["employee", "guard"])
def test_staff_superuser_flags_never_bypass_business_admin_role(client, actors, name):
    user = actors[name]
    user.is_staff = user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(user)
    assert client.get(reverse("accounts:assignments")).status_code == 403
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302


@pytest.mark.parametrize("model", [User, GuardAssignment, AuditLog])
def test_django_admin_registrations_are_read_only(actors, model):
    user = actors["admin"]
    user.is_staff = user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    request = RequestFactory().get("/admin/")
    request.user = user
    registered = admin.site._registry[model]
    assert registered.has_view_permission(request)
    assert not registered.has_add_permission(request)
    assert not registered.has_change_permission(request)
    assert not registered.has_delete_permission(request)
    assert registered.get_actions(request) == {}


def test_admin_login_uses_same_axes_protected_login(client):
    response = client.get(reverse("admin:login"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url
