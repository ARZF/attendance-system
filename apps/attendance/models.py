from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
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
