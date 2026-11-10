from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import login, logout
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.attendance.permissions import require_admin
from apps.attendance.selectors import has_open_assignments, has_pending_requests
from apps.audit.services import log_activity

from .models import User
from .selectors import get_user_by_username


@transaction.atomic
def seed_development_users(passwords):
    if settings.ENVIRONMENT not in {"development", "test"}:
        raise PermissionDenied("Seeding is allowed only in development and test settings.")

    results = []
    for role in User.Role:
        username = f"demo_{role.value.lower()}"
        existing = get_user_by_username(username)
        if existing is not None:
            results.append((existing, False))
            continue

        password = passwords.get(role)
        if not password:
            raise ValueError(f"Set SEED_{role.value}_PASSWORD to create {username}.")

        user = User(username=username, role=role)
        validate_password(password, user=user)
        user.set_password(password)
        user.full_clean()
        user.save(force_insert=True)
        log_activity(
            action="USER_CREATED", actor=None, target_employee=user,
            details={"role": role.value, "source": "development_seed"},
        )
        results.append((user, True))

    return results


@transaction.atomic
def change_role(*, actor, user_id, role):
    require_admin(actor)
    user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
    require_admin(actor)
    if role not in User.Role.values:
        raise ValidationError("Select a valid business role.")
    if user.role == role:
        return user
    if has_open_assignments(user.pk):
        raise ValidationError("End this user's open assignments before changing their role.")
    if has_pending_requests(user.pk):
        raise ValidationError("Resolve this user's pending requests before changing their role.")
    previous_role = user.role
    user.role = role
    user.save(update_fields=["role"])
    log_activity(
        action="ROLE_CHANGED", actor=actor, target_employee=user,
        details={"previous_role": previous_role, "role": role},
    )
    return user


@transaction.atomic
def login_user(*, request, user):
    locked_user = get_object_or_404(User.objects.select_for_update(), pk=user.pk)
    if not locked_user.is_active:
        raise PermissionDenied("This account is inactive.")
    login(request, user)
    # Persist the authenticated session inside the same transaction as its audit event.
    request.session.save()
    log_activity(action="LOGIN", actor=user, target_employee=user)


@transaction.atomic
def logout_user(*, request):
    user = request.user
    if user.is_authenticated:
        get_object_or_404(User.objects.select_for_update(), pk=user.pk)
    logout(request)
    if user.is_authenticated:
        log_activity(action="LOGOUT", actor=user, target_employee=user)
