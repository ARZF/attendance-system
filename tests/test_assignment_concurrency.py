from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.utils import timezone

from apps.accounts.services import change_role
from apps.attendance.models import GuardAssignment
from apps.attendance.services import assign_guard, end_assignment
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db(transaction=True)


def run_concurrently(operations, expected_errors=(ValidationError,)):
    barrier = Barrier(len(operations))

    def worker(operation):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            barrier.wait(timeout=10)
            try:
                operation()
                return pid, "ok"
            except expected_errors:
                return pid, "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(worker, operation) for operation in operations]
        results = [future.result(timeout=20) for future in futures]
    assert len({pid for pid, result in results}) == len(operations)
    return [result for pid, result in results]


@pytest.mark.parametrize("replace", [False, True])
def test_concurrent_creates_or_replacements_have_one_winner(actors, user_model, replace):
    third_guard = user_model.objects.create_user("third_guard", role="GUARD")
    current = None
    if replace:
        current = assign_guard(
            actor=actors["admin"], employee_id=actors["employee"].pk,
            guard_id=actors["guard"].pk, expected_assignment_id=None,
        )

    def operation(guard_id):
        return lambda: assign_guard(
            actor=actors["admin"], employee_id=actors["employee"].pk,
            guard_id=guard_id, expected_assignment_id=current.pk if current else None,
        )

    results = run_concurrently([
        operation(actors["other_guard"].pk), operation(third_guard.pk),
    ])
    assert sorted(results) == ["ok", "rejected"]
    assert GuardAssignment.objects.filter(ended_at__isnull=True).count() == 1
    assert GuardAssignment.objects.count() == (2 if replace else 1)
    action = "ASSIGNMENT_REPLACED" if replace else "ASSIGNMENT_CREATED"
    assert AuditLog.objects.filter(action=action).count() == 1
    if replace:
        current.refresh_from_db()
        active = GuardAssignment.objects.get(ended_at__isnull=True)
        assert current.ended_at == active.started_at
        assert current.ended_at > current.started_at


def test_concurrent_direct_closed_overlaps_are_rejected_by_database(actors):
    start = timezone.now() - timedelta(days=3)
    first_inserted = Event()
    second_inserting = Event()

    def insert(guard_id):
        GuardAssignment.objects.create(
            employee_id=actors["employee"].pk, guard_id=guard_id,
            started_at=start, ended_at=start + timedelta(days=1),
        )

    def first():
        with transaction.atomic():
            insert(actors["guard"].pk)
            first_inserted.set()
            assert second_inserting.wait(timeout=5)

    def release_first(execute, sql, params, many, context):
        if sql.startswith("INSERT INTO"):
            second_inserting.set()
        return execute(sql, params, many, context)

    def second():
        assert first_inserted.wait(timeout=5)
        with connection.execute_wrapper(release_first):
            insert(actors["other_guard"].pk)

    results = run_concurrently(
        [first, second],
        expected_errors=(IntegrityError,),
    )
    assert sorted(results) == ["ok", "rejected"]
    assert GuardAssignment.objects.count() == 1


def test_concurrent_guard_role_change_and_assignment_cannot_violate_roles(actors):
    results = run_concurrently([
        lambda: assign_guard(
            actor=actors["admin"], employee_id=actors["employee"].pk,
            guard_id=actors["guard"].pk, expected_assignment_id=None,
        ),
        lambda: change_role(
            actor=actors["admin"], user_id=actors["guard"].pk, role="EMPLOYEE"
        ),
    ])
    assert sorted(results) == ["ok", "rejected"]
    actors["guard"].refresh_from_db()
    if GuardAssignment.objects.exists():
        assert actors["guard"].role == "GUARD"
    else:
        assert actors["guard"].role == "EMPLOYEE"
    assert AuditLog.objects.count() == 1


def test_concurrent_end_and_replace_cannot_end_a_new_assignment(actors):
    initial = assign_guard(
        actor=actors["admin"], employee_id=actors["employee"].pk,
        guard_id=actors["guard"].pk, expected_assignment_id=None,
    )
    results = run_concurrently([
        lambda: end_assignment(
            actor=actors["admin"], employee_id=actors["employee"].pk, assignment_id=initial.pk,
        ),
        lambda: assign_guard(
            actor=actors["admin"], employee_id=actors["employee"].pk,
            guard_id=actors["other_guard"].pk, expected_assignment_id=initial.pk,
        ),
    ])
    assert sorted(results) == ["ok", "rejected"]
    initial.refresh_from_db()
    assert initial.ended_at is not None
    assert GuardAssignment.objects.filter(ended_at__isnull=True).count() == GuardAssignment.objects.count() - 1
    assert AuditLog.objects.count() == 2
