from django.contrib import messages
from django.contrib.auth.views import LoginView as DjangoLoginView, LogoutView as DjangoLogoutView
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.views import View

from apps.attendance.selectors import (
    assignment_history_for, assignment_management_data, employee_for_user, employees_visible_to,
)
from apps.attendance.services import assign_guard, end_assignment

from .forms import AssignmentForm, EndAssignmentForm, RoleChangeForm
from .permissions import AdminRequiredMixin, RoleRequiredMixin
from .selectors import all_users, user_by_id
from .services import change_role, login_user, logout_user


def render_page(request, page, context=None):
    directory = "accounts/partials" if request.headers.get("HX-Request") == "true" else "accounts"
    return render(request, f"{directory}/{page}.html", context or {})


class LoginView(DjangoLoginView):
    template_name = "registration/login.html"

    def form_valid(self, form):
        login_user(request=self.request, user=form.get_user())
        return HttpResponseRedirect(self.get_success_url())


class LogoutView(DjangoLogoutView):
    def post(self, request, *args, **kwargs):
        logout_user(request=request)
        return HttpResponseRedirect(self.get_success_url())


class HomeView(RoleRequiredMixin, View):
    def get(self, request):
        return render_page(request, "home")


class EmployeesView(RoleRequiredMixin, View):
    def get(self, request):
        return render_page(request, "employees", {"employees": employees_visible_to(request.user).order_by("username")})


class EmployeeDetailView(RoleRequiredMixin, View):
    def get(self, request, employee_id):
        employee = employee_for_user(request.user, employee_id)
        return render_page(request, "employee_detail", {
            "employee": employee, "assignments": assignment_history_for(employee.pk),
        })


class AssignmentManagementView(AdminRequiredMixin, View):
    def get(self, request):
        return render_page(request, "assignments", assignment_management_data())

    def post(self, request):
        action = request.POST.get("action")
        form_type = {"assign": AssignmentForm, "end": EndAssignmentForm}.get(action)
        errors = []
        if form_type is None:
            errors = ["Choose an assignment action."]
        else:
            form = form_type(request.POST)
            if not form.is_valid():
                errors = [message for field in form.errors.values() for message in field]
            else:
                service = assign_guard if action == "assign" else end_assignment
                try:
                    service(actor=request.user, **form.cleaned_data)
                except ValidationError as exc:
                    errors = exc.messages
        if not errors and request.headers.get("HX-Request") != "true":
            messages.success(request, "Assignment saved.")
            return redirect("accounts:assignments")
        context = assignment_management_data()
        context["errors"] = errors
        context["saved"] = not errors
        return render_page(request, "assignments", context)


class UsersView(AdminRequiredMixin, View):
    def get(self, request):
        return render_page(request, "users", {"users": all_users()})


class RoleChangeView(AdminRequiredMixin, View):
    def get(self, request, user_id):
        user = user_by_id(user_id)
        return render_page(request, "role_change", {"target_user": user, "form": RoleChangeForm(initial={"role": user.role})})

    def post(self, request, user_id):
        user = user_by_id(user_id)
        form = RoleChangeForm(request.POST)
        if form.is_valid():
            try:
                change_role(actor=request.user, user_id=user.pk, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
            else:
                messages.success(request, "Business role saved.")
                return redirect("accounts:home" if user.pk == request.user.pk else "accounts:users")
        return render_page(request, "role_change", {"target_user": user, "form": form})
