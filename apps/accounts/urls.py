from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("employees/", views.EmployeesView.as_view(), name="employees"),
    path("employees/<int:employee_id>/", views.EmployeeDetailView.as_view(), name="employee_detail"),
    path("assignments/", views.AssignmentManagementView.as_view(), name="assignments"),
    path("users/", views.UsersView.as_view(), name="users"),
    path("users/<int:user_id>/role/", views.RoleChangeView.as_view(), name="role_change"),
]
