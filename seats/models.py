"""Server A: Seats database (Movie, Showtime, Seat, Booking)."""
from django.db import models


class Movie(models.Model):
    title = models.CharField(max_length=100)
    genre = models.CharField(max_length=50, blank=True)
    duration_min = models.PositiveIntegerField()

    def __str__(self):
        return self.title


class Showtime(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="showtimes")
    hall = models.CharField(max_length=20)
    start_time = models.DateTimeField()
    ticket_price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return f"{self.movie} | {self.hall}"


class Seat(models.Model):
    AVAILABLE = "available"
    HELD = "held"          # reserved during Phase 1 (prepare), not yet final
    BOOKED = "booked"
    STATUS_CHOICES = [(AVAILABLE, "Available"), (HELD, "Held"), (BOOKED, "Booked")]

    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name="seats")
    row = models.CharField(max_length=1)
    number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=AVAILABLE)
    held_by_txn = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["row", "number"]
        unique_together = [("showtime", "row", "number")]

    @property
    def seat_no(self):
        return f"{self.row}{self.number}"

    def __str__(self):
        return f"Seat {self.seat_no} ({self.showtime})"


class Booking(models.Model):
    PENDING = "pending"        # created in Phase 1
    CONFIRMED = "confirmed"    # after global COMMIT
    CANCELLED = "cancelled"    # after global ABORT
    STATUS_CHOICES = [(PENDING, "Pending"), (CONFIRMED, "Confirmed"), (CANCELLED, "Cancelled")]

    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name="bookings")
    # The customer lives on Server B, so this is a plain number, not a ForeignKey.
    customer_id = models.IntegerField()
    txn_id = models.UUIDField(unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    booked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking {self.pk} for {self.seat.seat_no} ({self.status})"
