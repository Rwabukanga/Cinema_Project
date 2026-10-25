from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.views.generic import CreateView

from .forms import LoginForm, SignUpForm


class SignInView(LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)      # log out when the browser closes
        messages.success(self.request, f"Welcome back, {form.get_user().get_full_name() or form.get_user().username}!")
        return super().form_valid(form)


class SignUpView(CreateView):
    template_name = "accounts/signup.html"
    form_class = SignUpForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "starting_balance": settings.SIGNUP_STARTING_BALANCE}

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(
            self.request,
            f"Your account is ready. Your wallet starts with {settings.SIGNUP_STARTING_BALANCE}.",
        )
        return redirect("dashboard")
