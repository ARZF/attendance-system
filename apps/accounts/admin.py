from django.contrib import admin
from django.contrib.auth.models import Group

from apps.audit.admin import ReadOnlyModelAdmin

from .models import User

admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(ReadOnlyModelAdmin):
    list_display = ("username", "role", "is_active", "is_staff")
    fields = ("username", "email", "role", "is_active", "is_staff", "is_superuser", "date_joined")
    readonly_fields = fields
