from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class GuardAssignment(models.Model):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="guard_assignments",
    )
    guard = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="employee_assignments",
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(employee=models.F("guard")),
                name="attendance_assignment_not_self",
            ),
            models.CheckConstraint(
                condition=(models.Q(ended_at__isnull=True) | models.Q(ended_at__gt=models.F("started_at"))),
                name="attendance_assignment_dates_valid",
            ),
            models.UniqueConstraint(
                fields=["employee"], condition=models.Q(ended_at__isnull=True),
                name="attendance_one_open_assignment",
            ),
            ExclusionConstraint(
                name="attendance_assignment_no_overlap",
                expressions=[
                    ("employee", RangeOperators.EQUAL),
                    (
                        models.Func(
                            "started_at", "ended_at", RangeBoundary(),
                            function="TSTZRANGE", output_field=DateTimeRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]
        indexes = [
            models.Index(fields=["guard", "ended_at", "employee"], name="attendance_guard_scope_idx"),
        ]

    def __str__(self):
        return f"{self.employee_id} assigned to {self.guard_id}"


class AttendanceSession(models.Model):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_sessions",
    )
    check_in_at = models.DateTimeField()
    check_out_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-check_in_at", "-pk"]
        indexes = [
            models.Index(
                fields=["employee", "-check_in_at"],
                name="att_session_emp_checkin_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(check_out_at__isnull=True),
                name="attendance_one_active_session",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(check_out_at__isnull=True)
                    | models.Q(check_out_at__gt=models.F("check_in_at"))
                ),
                name="attendance_session_dates_valid",
            ),
            ExclusionConstraint(
                name="attendance_session_no_overlap",
                expressions=[
                    ("employee", RangeOperators.EQUAL),
                    (
                        models.Func(
                            "check_in_at",
                            "check_out_at",
                            RangeBoundary(),
                            function="TSTZRANGE",
                            output_field=DateTimeRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]

    def __str__(self):
        return f"Attendance session {self.pk} for user {self.employee_id}"


class AttendanceRequest(models.Model):
    class RequestType(models.TextChoices):
        CHECK_IN = "CHECK_IN", "Check in"
        CHECK_OUT = "CHECK_OUT", "Check out"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_requests",
    )
    request_type = models.CharField(max_length=16, choices=RequestType.choices)
    attendance_at = models.DateTimeField()
    requested_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_attendance_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="requests",
    )
    auto_approved = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["requested_at", "pk"]
        indexes = [
            models.Index(
                fields=["status", "request_type", "requested_at"],
                name="att_request_queue_idx",
            ),
            models.Index(
                fields=["employee", "status", "requested_at"],
                name="att_request_employee_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(request_type__in=["CHECK_IN", "CHECK_OUT"]),
                name="attendance_request_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["PENDING", "APPROVED", "REJECTED", "CANCELLED"]
                ),
                name="attendance_request_status_valid",
            ),
            models.UniqueConstraint(
                fields=["employee", "request_type"],
                condition=models.Q(status="PENDING"),
                name="attendance_one_pending_request_type",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="PENDING",
                        reviewed_by__isnull=True,
                        reviewed_at__isnull=True,
                        rejection_reason="",
                        auto_approved=False,
                    )
                    | (
                        models.Q(
                            status="APPROVED",
                            reviewed_at__isnull=False,
                            rejection_reason="",
                        )
                        & (
                            models.Q(auto_approved=True, reviewed_by__isnull=True)
                            | models.Q(auto_approved=False, reviewed_by__isnull=False)
                        )
                    )
                    | (
                        models.Q(
                            status="REJECTED",
                            reviewed_by__isnull=False,
                            reviewed_at__isnull=False,
                            auto_approved=False,
                        )
                        & ~models.Q(rejection_reason="")
                    )
                    | models.Q(
                        status="CANCELLED",
                        reviewed_by__isnull=True,
                        reviewed_at__isnull=True,
                        rejection_reason="",
                        auto_approved=False,
                    )
                ),
                name="attendance_request_review_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(request_type="CHECK_OUT", session__isnull=False)
                    | models.Q(
                        request_type="CHECK_IN",
                        status="APPROVED",
                        session__isnull=False,
                    )
                    | models.Q(
                        request_type="CHECK_IN",
                        status__in=["PENDING", "REJECTED", "CANCELLED"],
                        session__isnull=True,
                    )
                ),
                name="attendance_request_session_link_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(reviewed_by__isnull=True)
                    | ~models.Q(reviewed_by=models.F("employee"))
                ),
                name="attendance_request_not_self_reviewed",
            ),
        ]

    def __str__(self):
        return f"{self.get_request_type_display()} request {self.pk} for user {self.employee_id}"


class AttendanceCorrection(models.Model):
    class CorrectedField(models.TextChoices):
        CHECK_IN_AT = "CHECK_IN_AT", "Check-in time"
        CHECK_OUT_AT = "CHECK_OUT_AT", "Check-out time"

    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.PROTECT,
        related_name="corrections",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_corrections",
    )
    corrected_field = models.CharField(max_length=16, choices=CorrectedField.choices)
    previous_value = models.DateTimeField(null=True, blank=True)
    new_value = models.DateTimeField()
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(corrected_field__in=["CHECK_IN_AT", "CHECK_OUT_AT"]),
                name="attendance_correction_field_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(corrected_field="CHECK_OUT_AT")
                    | models.Q(previous_value__isnull=False)
                ),
                name="attendance_correction_previous_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(reason=""),
                name="attendance_correction_reason_required",
            ),
        ]

    def __str__(self):
        return f"Correction {self.pk} for attendance session {self.session_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Attendance corrections cannot be updated.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attendance corrections cannot be deleted.")
