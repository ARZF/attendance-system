from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.http import Http404
from django.utils import timezone

from apps.attendance.models import GuardAssignment
from apps.attendance.services import assign_guard, end_assignment
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def assign(actors, **overrides):
    arguments = dict(
        actor=actors["admin"], employee_id=actors["employee"].pk,
        guard_id=actors["guard"].pk, expected_assignment_id=None,
    )
    arguments.update(overrides)
    return assign_guard(**arguments)


def test_fresh_database_has_extension_and_exclusion_constraint():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")
        assert cursor.fetchone() == (1,)
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'attendance_assignment_no_overlap' AND contype = 'x'"
        )
        definition = cursor.fetchone()[0]
    assert "employee_id WITH =" in definition
    assert "tstzrange" in definition and "WITH &&" in definition


def test_create_replace_and_end_preserve_history_and_audit(actors):
    first = assign(actors)
    second = assign(
        actors, guard_id=actors["other_guard"].pk, expected_assignment_id=first.pk
    )
    first.refresh_from_db()
    assert first.ended_at == second.started_at
    assert first.ended_at > first.started_at
    assert second.ended_at is None

    ended = end_assignment(
        actor=actors["admin"], employee_id=actors["employee"].pk, assignment_id=second.pk
    )
    assert ended.ended_at > ended.started_at
    assert GuardAssignment.objects.count() == 2
    assert not GuardAssignment.objects.filter(ended_at__isnull=True).exists()
    assert list(AuditLog.objects.order_by("pk").values_list("action", flat=True)) == [
        "ASSIGNMENT_CREATED", "ASSIGNMENT_REPLACED", "ASSIGNMENT_ENDED"
    ]
    for log in AuditLog.objects.all():
        assert log.actor_id == actors["admin"].pk
        assert log.target_employee_id == actors["employee"].pk
    replacement = AuditLog.objects.get(action="ASSIGNMENT_REPLACED")
    assert replacement.details["previous_assignment_id"] == first.pk
    assert replacement.details["assignment_id"] == second.pk


def test_same_guard_is_noop_and_stale_submit_is_rejected(actors):
    first = assign(actors)
    assert assign(actors, expected_assignment_id=first.pk).pk == first.pk
    with pytest.raises(ValidationError, match="changed"):
        assign(actors)
    assert GuardAssignment.objects.count() == AuditLog.objects.count() == 1


@pytest.mark.parametrize("actor_name", ["employee", "guard"])
def test_assignment_services_require_admin(actors, actor_name):
    with pytest.raises(PermissionDenied):
        assign(actors, actor=actors[actor_name])
    first = assign(actors)
    with pytest.raises(PermissionDenied):
        end_assignment(
            actor=actors[actor_name], employee_id=actors["employee"].pk,
            assignment_id=first.pk,
        )


@pytest.mark.parametrize("field,name", [
    ("employee_id", "guard"), ("guard_id", "employee"),
    ("guard_id", "admin"), ("employee_id", "admin"),
])
def test_role_validation_runs_in_service(actors, field, name):
    with pytest.raises(ValidationError):
        assign(actors, **{field: actors[name].pk})
    assert not GuardAssignment.objects.exists()
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("name", ["employee", "guard"])
def test_inactive_assignment_participants_are_rejected(actors, name):
    participant = actors[name]
    participant.is_active = False
    participant.save(update_fields=["is_active"])
    with pytest.raises(ValidationError, match="active"):
        assign(actors)


def test_end_checks_employee_id_and_rejects_double_end(actors):
    first = assign(actors)
    with pytest.raises(Http404):
        end_assignment(
            actor=actors["admin"], employee_id=actors["other_employee"].pk,
            assignment_id=first.pk,
        )
    end_assignment(
        actor=actors["admin"], employee_id=actors["employee"].pk, assignment_id=first.pk
    )
    with pytest.raises(ValidationError, match="ended"):
        end_assignment(
            actor=actors["admin"], employee_id=actors["employee"].pk,
            assignment_id=first.pk,
        )


@pytest.mark.parametrize("operation", ["create", "replace", "end"])
def test_audit_failure_rolls_back_entire_assignment_action(actors, monkeypatch, operation):
    existing = assign(actors) if operation != "create" else None
    original = list(GuardAssignment.objects.values())

    def fail(**kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr("apps.attendance.services.log_activity", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        if operation == "end":
            end_assignment(
                actor=actors["admin"], employee_id=actors["employee"].pk,
                assignment_id=existing.pk,
            )
        else:
            assign(
                actors, guard_id=actors["other_guard"].pk,
                expected_assignment_id=existing.pk if existing else None,
            )
    assert list(GuardAssignment.objects.values()) == original


def test_database_rejects_overlapping_closed_periods(actors):
    start = timezone.now() - timedelta(days=3)
    GuardAssignment.objects.create(
        employee=actors["employee"], guard=actors["guard"],
        started_at=start, ended_at=start + timedelta(days=2),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        GuardAssignment.objects.create(
            employee=actors["employee"], guard=actors["other_guard"],
            started_at=start + timedelta(days=1), ended_at=start + timedelta(days=3),
        )


def test_database_allows_adjacent_periods_and_different_employees(actors):
    start = timezone.now() - timedelta(days=3)
    for employee, left, right in [
        (actors["employee"], start, start + timedelta(days=1)),
        (actors["employee"], start + timedelta(days=1), start + timedelta(days=2)),
        (actors["other_employee"], start, start + timedelta(days=2)),
    ]:
        GuardAssignment.objects.create(
            employee=employee, guard=actors["guard"], started_at=left, ended_at=right
        )
    assert GuardAssignment.objects.count() == 3


@pytest.mark.parametrize("kind", ["open_duplicate", "self", "zero_duration", "negative"])
def test_existing_database_constraints(actors, kind):
    start = timezone.now() - timedelta(days=1)
    data = dict(employee=actors["employee"], guard=actors["guard"], started_at=start)
    if kind == "open_duplicate":
        GuardAssignment.objects.create(**data)
    elif kind == "self":
        data["guard"] = actors["employee"]
    elif kind == "zero_duration":
        data["ended_at"] = start
    else:
        data["ended_at"] = start - timedelta(seconds=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        GuardAssignment.objects.create(**data)


def test_future_open_history_cannot_be_replaced_by_service(actors):
    existing = GuardAssignment.objects.create(
        employee=actors["employee"], guard=actors["guard"],
        started_at=timezone.now() + timedelta(days=1),
    )
    with pytest.raises(ValidationError):
        assign(actors, guard_id=actors["other_guard"].pk, expected_assignment_id=existing.pk)


def test_service_validates_closed_history_before_creating_assignment(actors):
    now = timezone.now()
    GuardAssignment.objects.create(
        employee=actors["employee"], guard=actors["guard"],
        started_at=now - timedelta(days=1), ended_at=now + timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="overlap"):
        assign(actors)
    assert not AuditLog.objects.exists()
