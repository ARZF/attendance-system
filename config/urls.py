from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("attendance/", include("apps.attendance.urls")),
    path("", include("apps.accounts.urls")),
]
