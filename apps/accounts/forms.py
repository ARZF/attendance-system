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


class BusinessUserCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=User.Role.choices)
    email = forms.EmailField(required=False)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    is_active = forms.BooleanField(required=False, initial=True)

    def clean_is_active(self):
        if "is_active" not in self.data:
            return True
        return self.cleaned_data["is_active"]


class BusinessUserUpdateForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)


class AccountStatusForm(forms.Form):
    is_active = forms.BooleanField(required=False)
