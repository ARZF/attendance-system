from urllib.parse import urlencode

from django.contrib.admin import AdminSite
from django.shortcuts import redirect
from django.urls import reverse


class BusinessAdminSite(AdminSite):
    def has_permission(self, request):
        return super().has_permission(request) and request.user.role == "ADMIN"

    def login(self, request, extra_context=None):
        destination = request.GET.get("next", reverse("admin:index"))
        return redirect(f"{reverse('accounts:login')}?{urlencode({'next': destination})}")

    def logout(self, request, extra_context=None):
        from apps.accounts.views import LogoutView

        return LogoutView.as_view()(request)
