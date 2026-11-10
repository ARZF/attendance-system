from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import reverse
from urllib.parse import urlencode


class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles = ("EMPLOYEE", "GUARD", "ADMIN")

    def handle_no_permission(self):
        if self.request.headers.get("HX-Request") == "true" and not self.request.user.is_authenticated:
            destination = f"{reverse('accounts:login')}?{urlencode({'next': self.request.get_full_path()})}"
            return HttpResponse(status=401, headers={"HX-Redirect": destination})
        return super().handle_no_permission()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_active or request.user.role not in self.allowed_roles:
            raise PermissionDenied("Your business role cannot access this page.")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ("ADMIN",)
