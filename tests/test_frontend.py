import pytest
from django.urls import reverse

from apps.attendance.services import assign_guard


pytestmark = pytest.mark.django_db


def test_attendance_page_requires_login(client):
    response = client.get(reverse("attendance:dashboard"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.parametrize("name", ["employee", "guard", "admin"])
def test_attendance_page_is_available_to_each_business_role(client, actors, name):
    client.force_login(actors[name])

    response = client.get(reverse("attendance:dashboard"))

    assert response.status_code == 200
    assert b'id="attendance-app"' in response.content
    assert b'static/js/attendance.js' in response.content
    assert b'name="csrf-token"' in response.content


def test_attendance_page_shows_only_role_relevant_workspaces(client, actors):
    client.force_login(actors["employee"])
    employee_page = client.get(reverse("attendance:dashboard")).content
    assert b'id="review-requests-body"' not in employee_page
    assert b'id="admin-audit-filter"' not in employee_page

    client.force_login(actors["guard"])
    guard_page = client.get(reverse("attendance:dashboard")).content
    assert b'id="review-requests-body"' in guard_page
    assert b'id="admin-audit-filter"' not in guard_page

    client.force_login(actors["admin"])
    admin_page = client.get(reverse("attendance:dashboard")).content
    assert b'id="review-requests-body"' in admin_page
    assert b'id="admin-audit-filter"' in admin_page


def test_guard_employee_selector_is_scoped_to_current_assignments(client, actors):
    assign_guard(
        actor=actors["admin"],
        employee_id=actors["employee"].pk,
        guard_id=actors["guard"].pk,
        expected_assignment_id=None,
    )
    client.force_login(actors["guard"])

    response = client.get(reverse("attendance:dashboard"))

    assert actors["employee"].username.encode() in response.content
    assert actors["other_employee"].username.encode() not in response.content


def test_authenticated_navigation_links_to_attendance(client, actors):
    client.force_login(actors["employee"])

    response = client.get(reverse("accounts:home"))

    assert reverse("attendance:dashboard").encode() in response.content


def test_admin_users_page_exposes_existing_management_apis(client, actors):
    client.force_login(actors["admin"])

    response = client.get(reverse("accounts:users"))

    assert response.status_code == 200
    assert b'id="create-user-form"' in response.content
    assert b'data-user-update=' in response.content
    assert b'data-user-status=' in response.content
    assert b'static/js/users.js' in response.content
