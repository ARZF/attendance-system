from django.contrib import admin

from apps.audit.admin import ReadOnlyModelAdmin

from .models import GuardAssignment


@admin.register(GuardAssignment)
class GuardAssignmentAdmin(ReadOnlyModelAdmin):
    list_display = ("employee", "guard", "started_at", "ended_at")
    readonly_fields = list_display
