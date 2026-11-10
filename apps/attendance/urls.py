from django.urls import path

from . import views

app_name = "attendance"
urlpatterns = [
    path("requests/check-in/", views.CheckInRequestView.as_view(), name="request_check_in"),
    path("requests/check-out/", views.CheckOutRequestView.as_view(), name="request_check_out"),
    path("requests/", views.OwnRequestHistoryView.as_view(), name="own_requests"),
    path(
        "requests/<int:request_id>/",
        views.OwnRequestDetailView.as_view(),
        name="own_request_detail",
    ),
    path(
        "requests/<int:request_id>/cancel/",
        views.CancelRequestView.as_view(),
        name="cancel_request",
    ),
    path(
        "requests/<int:request_id>/approve/",
        views.ReviewRequestView.as_view(),
        name="approve_request",
    ),
    path(
        "requests/<int:request_id>/reject/",
        views.RejectRequestView.as_view(),
        name="reject_request",
    ),
    path("history/", views.OwnAttendanceHistoryView.as_view(), name="own_history"),
    path(
        "guard/employees/",
        views.GuardAssignedEmployeesView.as_view(),
        name="guard_employees",
    ),
    path(
        "guard/requests/pending/",
        views.GuardPendingRequestsView.as_view(),
        name="guard_pending_requests",
    ),
    path(
        "guard/employees/<int:employee_id>/history/",
        views.ScopedEmployeeHistoryView.as_view(),
        name="scoped_employee_history",
    ),
    path(
        "sessions/<int:session_id>/correct/",
        views.CorrectSessionView.as_view(),
        name="correct_session",
    ),
    path(
        "sessions/<int:session_id>/close/",
        views.CloseSessionView.as_view(),
        name="close_session",
    ),
    path(
        "admin/requests/",
        views.AdminRequestHistoryView.as_view(),
        name="admin_requests",
    ),
    path(
        "admin/assignments/",
        views.AdminAssignmentHistoryView.as_view(),
        name="admin_assignments",
    ),
    path(
        "admin/audit/",
        views.AdminAuditHistoryView.as_view(),
        name="admin_audit",
    ),
    path("dashboard/employee/", views.EmployeeDashboardView.as_view(), name="employee_dashboard"),
    path("dashboard/guard/", views.GuardDashboardView.as_view(), name="guard_dashboard"),
    path("dashboard/admin/", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    path("reports/attendance/", views.AttendanceReportView.as_view(), name="attendance_report"),
]
