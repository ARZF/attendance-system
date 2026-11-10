from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="audit_actions",
    )
    target_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=64)
    details = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(
                fields=["created_at", "actor", "action"],
                name="audit_created_actor_action_idx",
            ),
        ]
