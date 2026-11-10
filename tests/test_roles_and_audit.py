import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.services import change_role
from apps.attendance.selectors import has_pending_requests
from apps.attendance.services import assign_guard, end_assignment
from apps.audit.models import AuditLog
from apps.audit.services import log_activity

pytestmark = pytest.mark.django_db


def test_role_change_is_audited_and_independent_of_staff_flags(actors):
    user = change_role(actor=actors["admin"], user_id=actors["employee"].pk, role="GUARD")
    assert user.role == "GUARD"
    assert not user.is_staff and not user.is_superuser
    log = AuditLog.objects.get(action="ROLE_CHANGED")
    assert log.actor_id == actors["admin"].pk
    assert log.target_employee_id == user.pk
    assert log.details == {"previous_role": "EMPLOYEE", "role": "GUARD"}


@pytest.mark.parametrize("name", ["employee", "guard"])
def test_role_change_requires_admin(actors, name):
    with pytest.raises(PermissionDenied):
        change_role(actor=actors[name], user_id=actors["other_employee"].pk, role="ADMIN")


@pytest.mark.parametrize("name", ["employee", "guard"])
def test_role_change_blocked_by_open_assignment_on_either_side(actors, name):
    assign_guard(
        actor=actors["admin"], employee_id=actors["employee"].pk,
        guard_id=actors["guard"].pk, expected_assignment_id=None,
    )
    with pytest.raises(ValidationError, match="assignment"):
        change_role(actor=actors["admin"], user_id=actors[name].pk, role="ADMIN")
    assert not AuditLog.objects.filter(action="ROLE_CHANGED").exists()


def test_pending_request_hook_blocks_role_change(actors, monkeypatch):
    monkeypatch.setattr("apps.accounts.services.has_pending_requests", lambda user_id: True)
    with pytest.raises(ValidationError, match="pending"):
        change_role(actor=actors["admin"], user_id=actors["employee"].pk, role="GUARD")
    assert not AuditLog.objects.exists()


def test_pending_request_selector_is_explicit_phase_three_stub(actors):
    assert has_pending_requests(actors["employee"].pk) is False


def test_closed_assignment_history_does_not_block_role_change(actors):
    assignment = assign_guard(
        actor=actors["admin"], employee_id=actors["employee"].pk,
        guard_id=actors["guard"].pk, expected_assignment_id=None,
    )
    end_assignment(actor=actors["admin"], employee_id=actors["employee"].pk, assignment_id=assignment.pk)
    user = change_role(actor=actors["admin"], user_id=actors["employee"].pk, role="GUARD")
    assert user.role == "GUARD"


def test_role_audit_failure_rolls_back_user_change(actors, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr("apps.accounts.services.log_activity", fail)
    with pytest.raises(RuntimeError):
        change_role(actor=actors["admin"], user_id=actors["employee"].pk, role="GUARD")
    actors["employee"].refresh_from_db()
    assert actors["employee"].role == "EMPLOYEE"


def test_role_noop_and_invalid_role_do_not_write_audit(actors):
    change_role(actor=actors["admin"], user_id=actors["employee"].pk, role="EMPLOYEE")
    with pytest.raises(ValidationError):
        change_role(actor=actors["admin"], user_id=actors["employee"].pk, role="INVALID")
    assert not AuditLog.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_log_activity_requires_action_transaction_and_allows_system_actor():
    with pytest.raises(RuntimeError, match="transaction"):
        log_activity(action="SYSTEM_EVENT", actor=None)
    with transaction.atomic():
        log = log_activity(action="SYSTEM_EVENT", actor=None, details={"source": "test"})
    assert log.actor_id is None
    assert log.details == {"source": "test"}
