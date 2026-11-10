from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import login, logout
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404

from apps.attendance.permissions import require_admin
from apps.attendance.selectors import has_open_assignments, has_pending_requests
from apps.audit.services import log_activity

from .models import User
from .security import get_client_ip
from .selectors import get_user_by_username


def _ensure_admin_will_remain(user, *, role=None, is_active=None):
    resulting_role = role if role is not None else user.role
    resulting_active = is_active if is_active is not None else user.is_active
    if user.role == User.Role.ADMIN and user.is_active and (
        resulting_role != User.Role.ADMIN or not resulting_active
    ):
        if not User.objects.select_for_update().filter(
            role=User.Role.ADMIN,
            is_active=True,
        ).exclude(pk=user.pk).exists():
            raise ValidationError("At least one active business administrator is required.")


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
            target=user,
            details={"role": role.value, "source": "development_seed"},
        )
        results.append((user, True))

    return results


@transaction.atomic
def change_role(*, actor, user_id, role, ip_address=None):
    require_admin(actor)
    user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
    require_admin(actor)
    if role not in User.Role.values:
        raise ValidationError("Select a valid business role.")
    if user.role == role:
        return user
    _ensure_admin_will_remain(user, role=role)
    if has_open_assignments(user.pk):
        raise ValidationError("End this user's open assignments before changing their role.")
    if has_pending_requests(user.pk):
        raise ValidationError("Resolve this user's pending requests before changing their role.")
    previous_role = user.role
    user.role = role
    user.save(update_fields=["role"])
    log_activity(
        action="ROLE_CHANGED", actor=actor, target_employee=user,
        target=user,
        details={"previous_role": previous_role, "role": role},
        ip_address=ip_address,
    )
    return user


@transaction.atomic
def create_business_user(
    *,
    actor,
    username,
    password,
    role,
    email="",
    first_name="",
    last_name="",
    is_active=True,
    ip_address=None,
):
    require_admin(actor)
    get_object_or_404(User.objects.select_for_update(), pk=actor.pk)
    require_admin(actor)
    if role not in User.Role.values:
        raise ValidationError("Select a valid business role.")
    user = User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=is_active,
    )
    validate_password(password, user=user)
    user.set_password(password)
    user.full_clean()
    try:
        user.save(force_insert=True)
    except IntegrityError as error:
        raise ValidationError("A user with this username already exists.") from error
    log_activity(
        action="USER_CREATED",
        actor=actor,
        target_employee=user,
        target=user,
        details={
            "username": user.username,
            "role": user.role,
            "is_active": user.is_active,
        },
        ip_address=ip_address,
    )
    return user


@transaction.atomic
def update_user_information(
    *,
    actor,
    user_id,
    username,
    email="",
    first_name="",
    last_name="",
    ip_address=None,
):
    require_admin(actor)
    user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
    require_admin(actor)
    before = {
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }
    user.username = username
    user.email = email
    user.first_name = first_name
    user.last_name = last_name
    user.full_clean()
    after = {
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }
    if before == after:
        return user
    try:
        user.save(update_fields=["username", "email", "first_name", "last_name"])
    except IntegrityError as error:
        raise ValidationError("A user with this username already exists.") from error
    log_activity(
        action="USER_UPDATED",
        actor=actor,
        target_employee=user,
        target=user,
        details={"before": before, "after": after},
        ip_address=ip_address,
    )
    return user


@transaction.atomic
def set_user_active(*, actor, user_id, is_active, ip_address=None):
    require_admin(actor)
    user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
    require_admin(actor)
    if user.is_active == is_active:
        return user
    if user.pk == actor.pk and not is_active:
        raise ValidationError("You cannot deactivate your own account.")
    if not is_active:
        _ensure_admin_will_remain(user, is_active=False)
        if has_open_assignments(user.pk):
            raise ValidationError("End this user's open assignments before deactivation.")
        if has_pending_requests(user.pk):
            raise ValidationError("Resolve this user's pending requests before deactivation.")
    previous = user.is_active
    user.is_active = is_active
    user.save(update_fields=["is_active"])
    log_activity(
        action="USER_ACTIVATED" if is_active else "USER_DEACTIVATED",
        actor=actor,
        target_employee=user,
        target=user,
        details={"previous_is_active": previous, "is_active": is_active},
        ip_address=ip_address,
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
    log_activity(
        action="LOGIN",
        actor=user,
        target_employee=user,
        target=user,
        ip_address=get_client_ip(request),
    )


@transaction.atomic
def logout_user(*, request):
    user = request.user
    if user.is_authenticated:
        get_object_or_404(User.objects.select_for_update(), pk=user.pk)
    logout(request)
    if user.is_authenticated:
        log_activity(
            action="LOGOUT",
            actor=user,
            target_employee=user,
            target=user,
            ip_address=get_client_ip(request),
        )
