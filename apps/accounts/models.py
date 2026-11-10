from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        GUARD = "GUARD", "Guard"
        ADMIN = "ADMIN", "Admin"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.EMPLOYEE)
    objects = UserManager()

    class Meta(AbstractUser.Meta):
        abstract = False
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["EMPLOYEE", "GUARD", "ADMIN"]),
                name="accounts_user_role_valid",
            ),
        ]
