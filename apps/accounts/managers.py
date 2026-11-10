from django.contrib.auth.models import UserManager as DjangoUserManager


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", self.model.Role.ADMIN)
        if extra_fields["role"] != self.model.Role.ADMIN:
            raise ValueError("A newly created superuser must have role ADMIN.")
        return super().create_superuser(
            username, email=email, password=password, **extra_fields
        )
