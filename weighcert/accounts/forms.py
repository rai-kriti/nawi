from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import SetPasswordForm
from .models import Profile


class LoginForm(forms.Form):
    username = forms.CharField(
        label="Officer ID / Government Email",
        widget=forms.TextInput(attrs={
            "class": "w-full bg-slate-50 border border-slate-300 rounded px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#012357]",
            "placeholder": "officer@gov.in or LM-12345",
            "autocomplete": "username",
            "required": True,
        })
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "w-full bg-slate-50 border border-slate-300 rounded px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#012357]",
            "placeholder": "Enter password",
            "autocomplete": "current-password",
            "required": True,
        })
    )


class ForcePasswordChangeForm(SetPasswordForm):
    pass


class UserCreateForm(forms.ModelForm):
    username = forms.CharField(max_length=150, label="Official Email / Username")
    first_name = forms.CharField(max_length=150, label="First Name")
    last_name = forms.CharField(max_length=150, label="Last Name")
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES, label="Role")
    designation = forms.CharField(max_length=200, label="Designation")
    employee_id = forms.CharField(max_length=50, label="Employee ID")
    temporary_password = forms.CharField(
        widget=forms.PasswordInput, required=True,
        help_text="User will be forced to change this on first login."
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["username"]
        user.set_password(self.cleaned_data["temporary_password"])
        if commit:
            user.save()
            profile = user.profile
            profile.role = self.cleaned_data["role"]
            profile.designation = self.cleaned_data["designation"]
            profile.employee_id = self.cleaned_data["employee_id"]
            profile.must_change_password = True
            profile.save()
        return user

