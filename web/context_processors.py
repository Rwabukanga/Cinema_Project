"""Data the navbar and sidebar need on every page."""
from django.urls import reverse
from django.utils.timesince import timesince

from coordinator.models import TransactionLog
from payments.models import Customer
from seats.models import Booking

STATE_ICON = {
    TransactionLog.COMMITTED: "bi-check-circle-fill text-success",
    TransactionLog.ABORTED: "bi-x-circle-fill text-danger",
    TransactionLog.PREPARED: "bi-hourglass-split text-warning",
    TransactionLog.STARTED: "bi-hourglass-split text-warning",
}


def navbar(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    logs = TransactionLog.objects.all()
    bookings = Booking.objects.filter(status=Booking.CONFIRMED)
    customer = getattr(user, "customer", None)
    if not user.is_staff:                      # a customer only sees their own activity
        own = customer.pk if customer else -1
        logs = logs.filter(customer_id=own)
        bookings = bookings.filter(customer_id=own)

    names = dict(Customer.objects.values_list("pk", "full_name"))

    notifications = [{
        "url": reverse("web:transaction_detail", args=[log.txn_id]),
        "icon": STATE_ICON.get(log.state, "bi-info-circle"),
        "text": f"{names.get(log.customer_id, 'Customer')}: {log.get_state_display()}",
        "when": timesince(log.created_at).split(",")[0],
    } for log in logs[:5]]

    latest = list(bookings.select_related("seat__showtime__movie").order_by("-booked_at")[:4])
    for b in latest:
        b.customer_name = names.get(b.customer_id, "Customer")
        b.ago = timesince(b.booked_at).split(",")[0]

    return {
        # open transactions = a 2PC left unfinished (e.g. coordinator crash)
        "alert_count": logs.filter(completed=False).count(),
        "nav_notifications": notifications,
        "nav_notification_count": len(notifications),
        "nav_latest_bookings": latest,
        "nav_new_bookings": len(latest),
        "nav_customer": customer,
    }
