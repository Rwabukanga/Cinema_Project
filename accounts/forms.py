from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from cinema_project.mixins import BootstrapFormMixin
from payments.models import Customer, Wallet


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    remember_me = forms.BooleanField(required=False, initial=True, label="Remember me")


class SignUpForm(BootstrapFormMixin, UserCreationForm):
    """
    Creates three things at once:
      1. a Django User (the login)
      2. a Customer on Server B linked to that user
      3. a Wallet with a starting balance, so the new user can book right away
    """

    first_name = forms.CharField(max_length=50)
    last_name = forms.CharField(max_length=50)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20, required=False)

    field_order = ["first_name", "last_name", "username", "email", "phone", "password1", "password2"]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["first_name", "last_name", "username", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists() or Customer.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.email = self.cleaned_data["email"]
            user.save()
            customer = Customer.objects.create(
                user=user,
                full_name=f"{user.first_name} {user.last_name}".strip(),
                email=user.email,
                phone=self.cleaned_data.get("phone", ""),
            )
            Wallet.objects.create(customer=customer, balance=Decimal(settings.SIGNUP_STARTING_BALANCE))
        return user
