"""Turn models into JSON (and JSON into models) for the REST API."""
from decimal import Decimal
from string import ascii_uppercase

from django.db import transaction
from rest_framework import serializers

from coordinator.models import TransactionLog
from coordinator.services import SCENARIOS
from payments.models import Customer, Payment, Wallet
from seats.models import Booking, Movie, Seat, Showtime


# --------------------------------------------------------------------- Server A
class MovieSerializer(serializers.ModelSerializer):
    showtime_count = serializers.SerializerMethodField()
    booked_seats = serializers.SerializerMethodField()

    class Meta:
        model = Movie
        fields = ["id", "title", "genre", "duration_min", "showtime_count", "booked_seats"]

    def get_showtime_count(self, obj):
        return getattr(obj, "n_showtimes", None) if hasattr(obj, "n_showtimes") else obj.showtimes.count()

    def get_booked_seats(self, obj):
        if hasattr(obj, "n_booked"):
            return obj.n_booked
        return Seat.objects.filter(showtime__movie=obj, status=Seat.BOOKED).count()


class ShowtimeSerializer(serializers.ModelSerializer):
    movie_title = serializers.CharField(source="movie.title", read_only=True)
    total_seats = serializers.SerializerMethodField()
    booked_seats = serializers.SerializerMethodField()
    held_seats = serializers.SerializerMethodField()
    occupancy = serializers.SerializerMethodField()
    # Only used when a showtime is created: its seats are generated automatically.
    rows = serializers.IntegerField(write_only=True, required=False, default=4, min_value=1, max_value=10)
    seats_per_row = serializers.IntegerField(write_only=True, required=False, default=6, min_value=1, max_value=20)

    class Meta:
        model = Showtime
        fields = [
            "id", "movie", "movie_title", "hall", "start_time", "ticket_price",
            "total_seats", "booked_seats", "held_seats", "occupancy", "rows", "seats_per_row",
        ]

    def _counts(self, obj):
        if not hasattr(obj, "_seat_counts"):
            if hasattr(obj, "n_total"):
                obj._seat_counts = (obj.n_total, obj.n_booked, obj.n_held)
            else:
                statuses = list(obj.seats.values_list("status", flat=True))
                obj._seat_counts = (len(statuses), statuses.count(Seat.BOOKED), statuses.count(Seat.HELD))
        return obj._seat_counts

    def get_total_seats(self, obj):
        return self._counts(obj)[0]

    def get_booked_seats(self, obj):
        return self._counts(obj)[1]

    def get_held_seats(self, obj):
        return self._counts(obj)[2]

    def get_occupancy(self, obj):
        total, booked, _ = self._counts(obj)
        return round(100 * booked / total) if total else 0

    def validate_ticket_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("The price must be more than 0.")
        return value

    def create(self, validated_data):
        rows = validated_data.pop("rows", 4)
        per_row = validated_data.pop("seats_per_row", 6)
        with transaction.atomic():
            showtime = Showtime.objects.create(**validated_data)
            Seat.objects.bulk_create(
                Seat(showtime=showtime, row=r, number=n)
                for r in ascii_uppercase[:rows] for n in range(1, per_row + 1)
            )
        return showtime

    def update(self, instance, validated_data):
        validated_data.pop("rows", None)          # seats can't be regenerated on edit
        validated_data.pop("seats_per_row", None)
        return super().update(instance, validated_data)


class SeatSerializer(serializers.ModelSerializer):
    seat_no = serializers.CharField(read_only=True)

    class Meta:
        model = Seat
        fields = ["id", "showtime", "row", "number", "seat_no", "status", "held_by_txn"]


class BookingSerializer(serializers.ModelSerializer):
    seat_no = serializers.CharField(source="seat.seat_no", read_only=True)
    showtime = serializers.IntegerField(source="seat.showtime_id", read_only=True)
    movie_title = serializers.CharField(source="seat.showtime.movie.title", read_only=True)
    start_time = serializers.DateTimeField(source="seat.showtime.start_time", read_only=True)
    hall = serializers.CharField(source="seat.showtime.hall", read_only=True)
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id", "txn_id", "status", "booked_at", "seat", "seat_no", "showtime",
            "movie_title", "start_time", "hall", "customer_id", "customer_name",
        ]

    def get_customer_name(self, obj):
        # The customer lives on Server B, so the view passes a {id: name} lookup.
        return self.context.get("customer_names", {}).get(obj.customer_id, "?")


# --------------------------------------------------------------------- Server B
class CustomerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True, default=None)
    balance = serializers.DecimalField(source="wallet.balance", max_digits=10, decimal_places=2, read_only=True)
    reserved = serializers.DecimalField(source="wallet.reserved", max_digits=10, decimal_places=2, read_only=True)
    available = serializers.DecimalField(source="wallet.available", max_digits=10, decimal_places=2, read_only=True)
    payments_count = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()
    initial_balance = serializers.DecimalField(
        max_digits=10, decimal_places=2, write_only=True, required=False,
        min_value=Decimal("0"), default=Decimal("100.00"),
    )

    class Meta:
        model = Customer
        fields = [
            "id", "full_name", "email", "phone", "username", "balance", "reserved", "available",
            "payments_count", "total_spent", "initial_balance",
        ]

    def _paid(self, obj):
        return Payment.objects.filter(wallet__customer=obj, status=Payment.PAID)

    def get_payments_count(self, obj):
        return getattr(obj, "n_paid", None) if hasattr(obj, "n_paid") else self._paid(obj).count()

    def get_total_spent(self, obj):
        if hasattr(obj, "spent"):
            return obj.spent or Decimal("0")
        return sum((p.amount for p in self._paid(obj)), Decimal("0"))

    def create(self, validated_data):
        balance = validated_data.pop("initial_balance", Decimal("100.00"))
        with transaction.atomic():
            customer = Customer.objects.create(**validated_data)
            Wallet.objects.create(customer=customer, balance=balance)
        return customer

    def update(self, instance, validated_data):
        validated_data.pop("initial_balance", None)
        return super().update(instance, validated_data)


class PaymentSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(source="wallet.customer_id", read_only=True)
    customer_name = serializers.CharField(source="wallet.customer.full_name", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "txn_id", "amount", "status", "created_at", "paid_at", "customer_id", "customer_name"]


class TopUpSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("1"))


# --------------------------------------------------------------------- Coordinator
class TransactionSerializer(serializers.ModelSerializer):
    state_display = serializers.CharField(source="get_state_display", read_only=True)
    customer_name = serializers.SerializerMethodField()
    seat_no = serializers.SerializerMethodField()
    movie_title = serializers.SerializerMethodField()
    showtime = serializers.SerializerMethodField()

    class Meta:
        model = TransactionLog
        fields = [
            "txn_id", "state", "state_display", "customer_id", "customer_name", "seat_id", "seat_no",
            "showtime", "movie_title", "amount", "seat_vote", "payment_vote", "completed", "message",
            "created_at", "updated_at",
        ]

    def _seat(self, obj):
        seats = self.context.setdefault("seats", {})
        if obj.seat_id not in seats:
            seats[obj.seat_id] = Seat.objects.select_related("showtime__movie").filter(pk=obj.seat_id).first()
        return seats[obj.seat_id]

    def get_customer_name(self, obj):
        names = self.context.get("customer_names")
        if names is None:
            names = self.context["customer_names"] = dict(Customer.objects.values_list("pk", "full_name"))
        return names.get(obj.customer_id, "?")

    def get_seat_no(self, obj):
        seat = self._seat(obj)
        return seat.seat_no if seat else None

    def get_movie_title(self, obj):
        seat = self._seat(obj)
        return seat.showtime.movie.title if seat else None

    def get_showtime(self, obj):
        seat = self._seat(obj)
        return seat.showtime_id if seat else None


class TransactionDetailSerializer(TransactionSerializer):
    """One transaction plus what each server did with it."""

    booking_status = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    seat_status = serializers.SerializerMethodField()
    start_time = serializers.SerializerMethodField()
    hall = serializers.SerializerMethodField()

    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + [
            "booking_status", "payment_status", "seat_status", "start_time", "hall",
        ]

    def get_booking_status(self, obj):
        return Booking.objects.filter(txn_id=obj.txn_id).values_list("status", flat=True).first()

    def get_payment_status(self, obj):
        return Payment.objects.filter(txn_id=obj.txn_id).values_list("status", flat=True).first()

    def get_seat_status(self, obj):
        seat = self._seat(obj)
        return seat.status if seat else None

    def get_start_time(self, obj):
        seat = self._seat(obj)
        return seat.showtime.start_time if seat else None

    def get_hall(self, obj):
        seat = self._seat(obj)
        return seat.showtime.hall if seat else None


class BookTicketSerializer(serializers.Serializer):
    seat = serializers.IntegerField()
    customer = serializers.IntegerField(required=False, help_text="Staff only: book for this customer.")
    scenario = serializers.ChoiceField(choices=[s for s, _ in SCENARIOS], default="none")

    def validate_seat(self, value):
        if not Seat.objects.filter(pk=value).exists():
            raise serializers.ValidationError("This seat does not exist.")
        return value
