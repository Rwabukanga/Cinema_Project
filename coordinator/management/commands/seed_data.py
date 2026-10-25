"""python manage.py seed_data  ->  fills the database with demo data and demo logins."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from coordinator.models import TransactionLog
from payments.models import Customer, Payment, Wallet
from seats.models import Booking, Movie, Seat, Showtime

ROWS = "ABCD"
SEATS_PER_ROW = 6
DEMO_PASSWORD = "demo12345"   # DEMO ONLY


class Command(BaseCommand):
    help = "Delete the cinema data and create demo movies, seats, customers and logins."

    def handle(self, *args, **options):
        User = get_user_model()

        TransactionLog.objects.all().delete()
        Booking.objects.all().delete()
        Seat.objects.all().delete()
        Showtime.objects.all().delete()
        Movie.objects.all().delete()
        Payment.objects.all().delete()
        Wallet.objects.all().delete()
        Customer.objects.all().delete()

        # Server A: movies, showtimes, seats
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        movies = [
            ("The Last Server", "Sci-Fi", 118, "Hall 1", 18, "75.00"),
            ("Commit or Abort", "Thriller", 102, "Hall 2", 20, "60.00"),
            ("Two Phases of Love", "Romance", 95, "Hall 3", 21, "90.00"),
        ]
        for title, genre, minutes, hall, hour, price in movies:
            movie = Movie.objects.create(title=title, genre=genre, duration_min=minutes)
            start = (now + timedelta(days=1)).replace(hour=hour)
            showtime = Showtime.objects.create(movie=movie, hall=hall, start_time=start, ticket_price=Decimal(price))
            Seat.objects.bulk_create(
                Seat(showtime=showtime, row=r, number=n) for r in ROWS for n in range(1, SEATS_PER_ROW + 1)
            )

        # Server B: customers, wallets and their logins
        customers = [
            ("alice", "Alice", "Uwase", "0780000001", "300.00"),
            ("brian", "Brian", "Mugisha", "0780000002", "150.00"),
            ("chloe", "Chloe", "Ineza", "0780000003", "40.00"),   # too little for a ticket
        ]
        for username, first, last, phone, balance in customers:
            email = f"{username}@example.com"
            user, _ = User.objects.get_or_create(
                username=username, defaults={"first_name": first, "last_name": last, "email": email}
            )
            user.set_password(DEMO_PASSWORD)
            user.save()
            c = Customer.objects.create(user=user, full_name=f"{first} {last}", email=email, phone=phone)
            Wallet.objects.create(customer=c, balance=Decimal(balance))

        # Staff login
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin12345")

        self.stdout.write(self.style.SUCCESS(
            f"Created {Movie.objects.count()} movies, {Seat.objects.count()} seats and {Customer.objects.count()} customers."
        ))
        self.stdout.write("Demo logins (DEMO ONLY):")
        self.stdout.write("  admin / admin12345   (staff: sees everything, can run recovery)")
        self.stdout.write(f"  alice, brian, chloe / {DEMO_PASSWORD}   (customers)")
