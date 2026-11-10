from django.contrib import admin

from .models import AuditLog


class ReadOnlyModelAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return self.admin_site.has_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.admin_site.has_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyModelAdmin):
    list_display = (
        "created_at",
        "actor",
        "target_employee",
        "action",
        "target_type",
        "target_id",
        "ip_address",
    )
    readonly_fields = (*list_display, "details")
