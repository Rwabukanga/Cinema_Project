"""
The REST API. Every web page gets its data from here, and every button calls it.

    /api/movies/            movies            (staff can add / edit / delete)
    /api/showtimes/         showtimes + seats (staff can add / edit / delete)
    /api/seats/             seats             (read only)
    /api/bookings/          bookings          (read only: made by two-phase commit)
    /api/customers/         customers+wallets (staff manage; a customer sees only themselves)
    /api/payments/          payments          (read only: made by two-phase commit)
    /api/transactions/      coordinator log   (read only) + /recover/ (staff)
    /api/book/              POST: book a seat with two-phase commit
    /api/dashboard/         numbers for the dashboard
    /api/me/                the logged-in user
"""
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from coordinator import services as coordinator
from coordinator.models import TransactionLog
from payments import services as payments_server
from payments.models import Customer, Payment
from seats.models import Booking, Movie, Seat, Showtime

from . import serializers as s
from .permissions import IsStaff, IsStaffOrReadOnly, customer_of


def customer_names():
    return dict(Customer.objects.values_list("pk", "full_name"))


def own_customer_id(request):
    """Staff: None (sees everything). Customer: their id. Anyone else: -1 (sees nothing)."""
    if request.user.is_staff:
        return None
    customer = customer_of(request.user)
    return customer.pk if customer else -1


def int_param(request, name):
    value = request.query_params.get(name, "")
    return int(value) if value.isdigit() else None


# =========================================================================== Server A
class MovieViewSet(viewsets.ModelViewSet):
    serializer_class = s.MovieSerializer
    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]

    def get_queryset(self):
        return Movie.objects.annotate(
            n_showtimes=Count("showtimes", distinct=True),
            n_booked=Count("showtimes__seats", filter=Q(showtimes__seats__status=Seat.BOOKED)),
        ).order_by("title")

    def destroy(self, request, *args, **kwargs):
        movie = self.get_object()
        if Booking.objects.filter(seat__showtime__movie=movie, status=Booking.CONFIRMED).exists():
            return Response({"detail": "This movie has confirmed bookings, so it can't be deleted."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


class ShowtimeViewSet(viewsets.ModelViewSet):
    serializer_class = s.ShowtimeSerializer
    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]

    def get_queryset(self):
        qs = Showtime.objects.select_related("movie").annotate(
            n_total=Count("seats"),
            n_booked=Count("seats", filter=Q(seats__status=Seat.BOOKED)),
            n_held=Count("seats", filter=Q(seats__status=Seat.HELD)),
        ).order_by("start_time")
        movie = int_param(self.request, "movie")
        return qs.filter(movie_id=movie) if movie else qs

    def destroy(self, request, *args, **kwargs):
        showtime = self.get_object()
        if Booking.objects.filter(seat__showtime=showtime, status=Booking.CONFIRMED).exists():
            return Response({"detail": "This showtime has confirmed bookings, so it can't be deleted."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True)
    def seats(self, request, pk=None):
        """GET /api/showtimes/<id>/seats/  ->  every seat of this showtime."""
        showtime = self.get_object()
        return Response(s.SeatSerializer(showtime.seats.all(), many=True).data)


class SeatViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.SeatSerializer

    def get_queryset(self):
        qs = Seat.objects.all()
        showtime = int_param(self.request, "showtime")
        return qs.filter(showtime_id=showtime) if showtime else qs


class BookingViewSet(viewsets.ReadOnlyModelViewSet):
    """Bookings are only created by POST /api/book/ (two-phase commit)."""

    serializer_class = s.BookingSerializer

    def get_queryset(self):
        qs = Booking.objects.select_related("seat__showtime__movie").order_by("-booked_at")
        own = own_customer_id(self.request)
        if own is not None:
            qs = qs.filter(customer_id=own)
        for name, field in (("showtime", "seat__showtime_id"), ("customer", "customer_id")):
            value = int_param(self.request, name)
            if value:
                qs = qs.filter(**{field: value})
        status_param = self.request.query_params.get("status")
        return qs.filter(status=status_param) if status_param else qs

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "customer_names": customer_names()}


# =========================================================================== Server B
class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = s.CustomerSerializer

    def get_queryset(self):
        qs = Customer.objects.select_related("wallet", "user").annotate(
            n_paid=Count("wallet__payments", filter=Q(wallet__payments__status=Payment.PAID)),
            spent=Sum("wallet__payments__amount", filter=Q(wallet__payments__status=Payment.PAID)),
        ).order_by("full_name")
        own = own_customer_id(self.request)
        return qs if own is None else qs.filter(pk=own)

    def check_permissions(self, request):
        super().check_permissions(request)
        # Creating, editing and deleting customers is for staff. Top-up has its own check.
        if self.action in ("create", "update", "partial_update", "destroy") and not request.user.is_staff:
            raise PermissionDenied("Only staff can change customers.")

    def destroy(self, request, *args, **kwargs):
        customer = self.get_object()
        if Payment.objects.filter(wallet__customer=customer).exists():
            return Response({"detail": "This customer has payments, so it can't be deleted."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="top-up")
    def top_up(self, request, pk=None):
        """POST /api/customers/<id>/top-up/  {"amount": 50}  ->  add money to the wallet."""
        customer = self.get_object()          # a customer can only reach their own record
        form = s.TopUpSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        payments_server.top_up(customer.pk, form.validated_data["amount"])
        return Response(self.get_serializer(self.get_queryset().get(pk=customer.pk)).data)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """Payments are only created by two-phase commit."""

    serializer_class = s.PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.select_related("wallet__customer").order_by("-created_at")
        own = own_customer_id(self.request)
        if own is not None:
            qs = qs.filter(wallet__customer_id=own)
        customer = int_param(self.request, "customer")
        return qs.filter(wallet__customer_id=customer) if customer else qs


# =========================================================================== Coordinator
class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    def get_serializer_class(self):
        return s.TransactionDetailSerializer if self.action == "retrieve" else s.TransactionSerializer

    def get_queryset(self):
        qs = TransactionLog.objects.all()
        own = own_customer_id(self.request)
        if own is not None:
            qs = qs.filter(customer_id=own)
        customer = int_param(self.request, "customer")
        if customer:
            qs = qs.filter(customer_id=customer)
        if self.request.query_params.get("open") == "1":
            qs = qs.filter(completed=False)
        return qs

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "customer_names": customer_names()}

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated, IsStaff])
    def recover(self, request):
        """POST /api/transactions/recover/  ->  finish every transaction left open by a crash."""
        results = coordinator.recover()
        return Response({
            "recovered": len(results),
            "results": [{"txn_id": str(txn), "action": what} for txn, what in results],
        })


class BookTicketView(APIView):
    """
    POST /api/book/   {"seat": 12, "scenario": "none"}         (customer: books for themselves)
                      {"seat": 12, "customer": 3, ...}          (staff: books for any customer)

    Runs the two-phase commit and returns the coordinator's transaction.
    """

    def post(self, request):
        form = s.BookTicketSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        if request.user.is_staff:
            customer_id = data.get("customer")
            if not customer_id or not Customer.objects.filter(pk=customer_id).exists():
                return Response({"customer": ["Choose a customer."]}, status=status.HTTP_400_BAD_REQUEST)
        else:
            customer = customer_of(request.user)
            if customer is None:
                return Response({"detail": "Your account has no customer wallet."}, status=status.HTTP_400_BAD_REQUEST)
            customer_id = customer.pk

        crashed = None
        try:
            log = coordinator.book_ticket(customer_id, data["seat"], data["scenario"])
        except coordinator.SimulatedCrash as exc:
            crashed = str(exc)
            log = TransactionLog.objects.filter(customer_id=customer_id, seat_id=data["seat"]).first()

        body = s.TransactionDetailSerializer(log, context={"request": request}).data
        body["crashed"] = crashed
        code = status.HTTP_201_CREATED if log.state == TransactionLog.COMMITTED else status.HTTP_200_OK
        return Response(body, status=code)


class DashboardView(APIView):
    """GET /api/dashboard/  ->  everything the dashboard shows."""

    def get(self, request):
        seats = Seat.objects.aggregate(total=Count("id"), booked=Count("id", filter=Q(status=Seat.BOOKED)))
        txns = TransactionLog.objects.all()
        own = own_customer_id(request)
        if own is not None:
            txns = txns.filter(customer_id=own)
        states = dict(txns.order_by().values_list("state").annotate(n=Count("pk")))

        upcoming = Showtime.objects.filter(start_time__gte=timezone.now()).select_related("movie").annotate(
            n_total=Count("seats"),
            n_booked=Count("seats", filter=Q(seats__status=Seat.BOOKED)),
            n_held=Count("seats", filter=Q(seats__status=Seat.HELD)),
        ).order_by("start_time")

        customer = customer_of(request.user)
        return Response({
            "is_staff": request.user.is_staff,
            "movies": Movie.objects.count(),
            "upcoming_showtimes": upcoming.count(),
            "seats_total": seats["total"],
            "seats_booked": seats["booked"],
            "occupancy": round(100 * seats["booked"] / seats["total"]) if seats["total"] else 0,
            "revenue": Payment.objects.filter(status=Payment.PAID).aggregate(s=Sum("amount"))["s"] or 0,
            "customers": Customer.objects.count(),
            "committed": states.get(TransactionLog.COMMITTED, 0),
            "aborted": states.get(TransactionLog.ABORTED, 0),
            "open": txns.filter(completed=False).count(),
            "recent_transactions": s.TransactionSerializer(
                txns[:8], many=True, context={"customer_names": customer_names()}
            ).data,
            "upcoming": s.ShowtimeSerializer(upcoming[:6], many=True).data,
            "my_customer": s.CustomerSerializer(customer).data if customer else None,
        })


class MeView(APIView):
    """GET /api/me/  ->  who is logged in."""

    def get(self, request):
        user = request.user
        customer = customer_of(user)
        return Response({
            "id": user.pk,
            "username": user.username,
            "full_name": user.get_full_name(),
            "email": user.email,
            "is_staff": user.is_staff,
            "customer": s.CustomerSerializer(customer).data if customer else None,
        })
