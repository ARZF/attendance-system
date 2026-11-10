from django.contrib import admin

from apps.audit.admin import ReadOnlyModelAdmin

from .models import (
    AttendanceCorrection,
    AttendanceRequest,
    AttendanceSession,
    GuardAssignment,
)


@admin.register(GuardAssignment)
class GuardAssignmentAdmin(ReadOnlyModelAdmin):
    list_display = ("employee", "guard", "started_at", "ended_at")
    readonly_fields = list_display


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(ReadOnlyModelAdmin):
    list_display = ("employee", "check_in_at", "check_out_at", "created_at")
    readonly_fields = (*list_display, "updated_at")


@admin.register(AttendanceRequest)
class AttendanceRequestAdmin(ReadOnlyModelAdmin):
    list_display = (
        "employee",
        "request_type",
        "attendance_at",
        "status",
        "requested_at",
        "reviewed_by",
    )
    readonly_fields = (
        *list_display,
        "reviewed_at",
        "rejection_reason",
        "session",
        "auto_approved",
        "updated_at",
    )


@admin.register(AttendanceCorrection)
class AttendanceCorrectionAdmin(ReadOnlyModelAdmin):
    list_display = (
        "session",
        "corrected_by",
        "corrected_field",
        "previous_value",
        "new_value",
        "created_at",
    )
    readonly_fields = (*list_display, "reason")
