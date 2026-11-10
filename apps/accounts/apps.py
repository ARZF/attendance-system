from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from . import signals  # noqa: F401


class AttendanceAdminConfig(AdminConfig):
    default_site = "config.admin.BusinessAdminSite"
