"""
The AdminLTE pages.

These views only send the page "shell" (layout, empty tables, forms).
The data is loaded by JavaScript from the REST API (/api/...), and every
button (add, edit, delete, book, top up, recover) calls the API too.
See static/js/app.js.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from coordinator.models import TransactionLog
from coordinator.services import SCENARIOS
from payments.models import Customer
from seats.models import Showtime


class Page(LoginRequiredMixin, TemplateView):
    """A page that needs a logged-in user."""


class StaffPage(UserPassesTestMixin, Page):
    def test_func(self):
        return self.request.user.is_staff


class DashboardView(Page):
    template_name = "dashboard.html"


# ---------------------------------------------------------------- Server A
class MovieListView(Page):
    template_name = "web/movie_list.html"


class ShowtimeListView(Page):
    template_name = "web/showtime_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        movie = self.request.GET.get("movie", "")
        ctx["movie_filter"] = movie if movie.isdigit() else ""
        return ctx


class ShowtimeDetailView(Page):
    """The seat map and the booking form."""

    template_name = "web/showtime_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["showtime"] = get_object_or_404(Showtime.objects.select_related("movie"), pk=kwargs["pk"])
        ctx["scenarios"] = SCENARIOS
        return ctx


class BookingListView(Page):
    template_name = "web/booking_list.html"


# ---------------------------------------------------------------- Server B
class CustomerListView(StaffPage):
    template_name = "web/customer_list.html"


class CustomerDetailView(Page):
    """A customer's wallet, payments and bookings. Customers can only open their own."""

    template_name = "web/customer_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = get_object_or_404(Customer, pk=kwargs["pk"])
        if not self.request.user.is_staff and customer.user_id != self.request.user.pk:
            raise PermissionDenied
        ctx["customer"] = customer
        return ctx


class MyWalletView(LoginRequiredMixin, View):
    def get(self, request):
        customer = getattr(request.user, "customer", None)
        if customer is None:
            messages.info(request, "Your account is a staff account without a wallet. Here are all customers.")
            return redirect("web:customer_list")
        return redirect("web:customer_detail", pk=customer.pk)


class PaymentListView(Page):
    template_name = "web/payment_list.html"


# ---------------------------------------------------------------- Coordinator
class TransactionListView(Page):
    template_name = "web/transaction_list.html"


class TransactionDetailView(Page):
    template_name = "web/transaction_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        log = get_object_or_404(TransactionLog, pk=kwargs["pk"])
        customer = getattr(self.request.user, "customer", None)
        if not self.request.user.is_staff and (customer is None or log.customer_id != customer.pk):
            raise PermissionDenied
        ctx["log"] = log
        return ctx


class ApiGuideView(Page):
    """A page listing every API endpoint (handy for the presentation)."""

    template_name = "web/api_guide.html"
