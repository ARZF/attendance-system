from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import AttendanceRequest


class DateRangeForm(forms.Form):
    start_date = forms.DateField(required=False)
    end_date = forms.DateField(required=False)
    employee_id = forms.IntegerField(min_value=1, required=False)
    page = forms.IntegerField(min_value=1, required=False, initial=1)
    page_size = forms.IntegerField(min_value=1, max_value=100, required=False, initial=25)
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("-check_in_at", "Newest check-in"),
            ("check_in_at", "Oldest check-in"),
            ("-check_out_at", "Newest check-out"),
            ("check_out_at", "Oldest check-out"),
            ("employee__username", "Employee username"),
            ("-employee__username", "Employee username descending"),
        ],
    )

    def clean(self):
        cleaned = super().clean()
        end_date = cleaned.get("end_date") or timezone.localdate()
        start_date = cleaned.get("start_date") or end_date - timedelta(days=29)
        if start_date > end_date:
            raise forms.ValidationError("Start date must not be after end date.")
        cleaned["start_date"] = start_date
        cleaned["end_date"] = end_date
        cleaned["page"] = cleaned.get("page") or 1
        cleaned["page_size"] = cleaned.get("page_size") or 25
        cleaned["sort"] = cleaned.get("sort") or "-check_in_at"
        return cleaned


class AttendanceTimestampForm(forms.Form):
    attendance_at = forms.DateTimeField()


class RejectionForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea)


class CorrectionForm(forms.Form):
    corrected_field = forms.ChoiceField(
        choices=[
            ("CHECK_IN_AT", "Check-in time"),
            ("CHECK_OUT_AT", "Check-out time"),
        ]
    )
    new_value = forms.DateTimeField()
    reason = forms.CharField(widget=forms.Textarea)


class CloseSessionForm(forms.Form):
    check_out_at = forms.DateTimeField()
    reason = forms.CharField(widget=forms.Textarea)


class PaginationForm(forms.Form):
    page = forms.IntegerField(min_value=1, required=False, initial=1)
    page_size = forms.IntegerField(min_value=1, max_value=100, required=False, initial=25)

    def clean(self):
        cleaned = super().clean()
        cleaned["page"] = cleaned.get("page") or 1
        cleaned["page_size"] = cleaned.get("page_size") or 25
        return cleaned


class RequestFilterForm(PaginationForm):
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All"), *AttendanceRequest.Status.choices],
    )
    request_type = forms.ChoiceField(
        required=False,
        choices=[("", "All"), *AttendanceRequest.RequestType.choices],
    )
    employee_id = forms.IntegerField(min_value=1, required=False)


class AuditFilterForm(PaginationForm):
    actor_id = forms.IntegerField(min_value=1, required=False)
    target_employee_id = forms.IntegerField(min_value=1, required=False)
    action = forms.CharField(max_length=64, required=False)
    target_type = forms.CharField(max_length=100, required=False)
    target_id = forms.CharField(max_length=64, required=False)
    start_date = forms.DateField(required=False)
    end_date = forms.DateField(required=False)

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("start_date")
            and cleaned.get("end_date")
            and cleaned["start_date"] > cleaned["end_date"]
        ):
            raise forms.ValidationError("Start date must not be after end date.")
        return cleaned
