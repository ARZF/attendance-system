from django import forms

from .models import User


class AssignmentForm(forms.Form):
    employee_id = forms.IntegerField(min_value=1)
    guard_id = forms.IntegerField(min_value=1)
    expected_assignment_id = forms.IntegerField(min_value=1, required=False)


class EndAssignmentForm(forms.Form):
    employee_id = forms.IntegerField(min_value=1)
    assignment_id = forms.IntegerField(min_value=1)


class RoleChangeForm(forms.Form):
    role = forms.ChoiceField(choices=User.Role.choices, label="Business role")
