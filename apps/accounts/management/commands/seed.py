import os

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.accounts.services import seed_development_users


class Command(BaseCommand):
    help = "Create missing demo accounts in development/test without changing existing users."

    def handle(self, *args, **options):
        passwords = {
            role: os.environ.get(f"SEED_{role.value}_PASSWORD") for role in User.Role
        }
        try:
            results = seed_development_users(passwords)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        except (PermissionDenied, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        for user, created in results:
            self.stdout.write(f"{'Created' if created else 'Unchanged'}: {user.username}")
