"""REST API, sign up / log in, and the pages.   Run:  python manage.py test"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from coordinator.models import TransactionLog
from payments.models import Customer, Wallet
from seats.models import Movie, Seat, Showtime


class ApiTestCase(TestCase):
    def setUp(self):
        call_command("seed_data", stdout=StringIO())
        self.admin = APIClient()
        self.admin.login(username="admin", password="admin12345")
        self.alice = APIClient()
        self.alice.login(username="alice", password="demo12345")
        self.alice_customer = Customer.objects.get(user__username="alice")
        self.seat = Seat.objects.filter(showtime__ticket_price=Decimal("75.00")).first()


class AuthTests(ApiTestCase):
    def test_api_needs_login(self):
        response = APIClient().get(reverse("api:movie-list"))
        self.assertEqual(response.status_code, 403)

    def test_basic_auth_works_for_tools(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Basic YWxpY2U6ZGVtbzEyMzQ1")   # alice:demo12345
        self.assertEqual(client.get(reverse("api:me")).data["username"], "alice")


class CinemaApiTests(ApiTestCase):
    def test_everyone_can_read_movies_and_showtimes(self):
        self.assertEqual(len(self.alice.get(reverse("api:movie-list")).data), 3)
        showtimes = self.alice.get(reverse("api:showtime-list")).data
        self.assertEqual(showtimes[0]["total_seats"], 24)
        seats = self.alice.get(reverse("api:showtime-seats", args=[showtimes[0]["id"]])).data
        self.assertEqual(len(seats), 24)

    def test_only_staff_can_add_movies(self):
        data = {"title": "New Film", "genre": "Drama", "duration_min": 100}
        self.assertEqual(self.alice.post(reverse("api:movie-list"), data).status_code, 403)
        self.assertEqual(self.admin.post(reverse("api:movie-list"), data).status_code, 201)

    def test_creating_a_showtime_creates_its_seats(self):
        movie = Movie.objects.first()
        response = self.admin.post(reverse("api:showtime-list"), {
            "movie": movie.pk, "hall": "Hall 9", "start_time": "2030-01-01T18:00",
            "ticket_price": "50.00", "rows": 3, "seats_per_row": 5,
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["total_seats"], 15)

    def test_validation_errors_come_back_per_field(self):
        response = self.admin.post(reverse("api:showtime-list"), {"hall": "X", "ticket_price": "0"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("movie", response.data)
        self.assertIn("ticket_price", response.data)

    def test_cannot_delete_a_showtime_with_confirmed_bookings(self):
        self.alice.post(reverse("api:book"), {"seat": self.seat.pk})
        response = self.admin.delete(reverse("api:showtime-detail", args=[self.seat.showtime_id]))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Showtime.objects.filter(pk=self.seat.showtime_id).exists())


class BookingApiTests(ApiTestCase):
    def test_customer_books_for_themselves(self):
        response = self.alice.post(reverse("api:book"), {"seat": self.seat.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["state"], "committed")
        self.assertEqual(response.data["customer_id"], self.alice_customer.pk)
        self.assertEqual(response.data["booking_status"], "confirmed")
        self.assertEqual(Wallet.objects.get(customer=self.alice_customer).balance, Decimal("225.00"))

    def test_customer_cannot_book_for_someone_else(self):
        brian = Customer.objects.get(user__username="brian")
        response = self.alice.post(reverse("api:book"), {"seat": self.seat.pk, "customer": brian.pk}, format="json")
        self.assertEqual(response.data["customer_id"], self.alice_customer.pk)   # "customer" is ignored

    def test_staff_must_choose_a_customer(self):
        self.assertEqual(self.admin.post(reverse("api:book"), {"seat": self.seat.pk}).status_code, 400)
        chloe = Customer.objects.get(user__username="chloe")
        response = self.admin.post(reverse("api:book"), {"seat": self.seat.pk, "customer": chloe.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "aborted")          # chloe has only 40

    def test_crash_then_recovery_through_the_api(self):
        response = self.alice.post(reverse("api:book"), {"seat": self.seat.pk, "scenario": "coordinator_crash"})
        self.assertEqual(response.data["state"], "prepared")
        self.assertTrue(response.data["crashed"])
        self.assertEqual(self.alice.post(reverse("api:transaction-recover")).status_code, 403)   # staff only
        result = self.admin.post(reverse("api:transaction-recover")).data
        self.assertEqual(result["recovered"], 1)
        self.assertEqual(TransactionLog.objects.get().state, TransactionLog.ABORTED)

    def test_customers_only_see_their_own_data(self):
        brian_client = APIClient()
        brian_client.login(username="brian", password="demo12345")
        self.alice.post(reverse("api:book"), {"seat": self.seat.pk})
        self.assertEqual(len(brian_client.get(reverse("api:transaction-list")).data), 0)
        self.assertEqual(len(brian_client.get(reverse("api:booking-list")).data), 0)
        self.assertEqual(len(brian_client.get(reverse("api:customer-list")).data), 1)
        self.assertEqual(len(self.admin.get(reverse("api:transaction-list")).data), 1)
        txn = TransactionLog.objects.get()
        self.assertEqual(brian_client.get(reverse("api:transaction-detail", args=[txn.pk])).status_code, 404)

    def test_top_up(self):
        url = reverse("api:customer-top-up", args=[self.alice_customer.pk])
        self.assertEqual(self.alice.post(url, {"amount": "0"}).status_code, 400)
        self.assertEqual(self.alice.post(url, {"amount": "25"}).data["balance"], "325.00")
        brian = Customer.objects.get(user__username="brian")
        other = reverse("api:customer-top-up", args=[brian.pk])
        self.assertEqual(self.alice.post(other, {"amount": "25"}).status_code, 404)   # not hers

    def test_dashboard(self):
        self.alice.post(reverse("api:book"), {"seat": self.seat.pk})
        data = self.alice.get(reverse("api:dashboard")).data
        self.assertEqual(data["committed"], 1)
        self.assertEqual(data["seats_booked"], 1)
        self.assertEqual(data["my_customer"]["available"], "225.00")


class AccountTests(TestCase):
    def test_signup_creates_user_customer_and_wallet_and_logs_in(self):
        response = self.client.post(reverse("signup"), {
            "first_name": "Diane", "last_name": "Keza", "username": "diane", "email": "diane@example.com",
            "phone": "0780000009", "password1": "S3cure-pass-42", "password2": "S3cure-pass-42",
        })
        self.assertRedirects(response, reverse("dashboard"))
        customer = Customer.objects.get(user__username="diane")
        self.assertEqual(customer.full_name, "Diane Keza")
        self.assertEqual(customer.wallet.balance, Decimal("200.00"))
        self.assertEqual(self.client.get(reverse("api:me")).data["username"], "diane")

    def test_signup_rejects_a_used_email(self):
        User.objects.create_user("x", "taken@example.com", "pw")
        response = self.client.post(reverse("signup"), {
            "first_name": "A", "last_name": "B", "username": "ab", "email": "taken@example.com",
            "password1": "S3cure-pass-42", "password2": "S3cure-pass-42",
        })
        self.assertContains(response, "already exists")

    def test_login_and_logout(self):
        User.objects.create_user("bob", "bob@example.com", "S3cure-pass-42")
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("login") + "?next=/")
        response = self.client.post(reverse("login"), {"username": "bob", "password": "S3cure-pass-42"})
        self.assertRedirects(response, reverse("dashboard"))
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))


class PageTests(ApiTestCase):
    def test_every_page_loads_for_staff(self):
        self.client.login(username="admin", password="admin12345")
        showtime = Showtime.objects.first()
        log_id = self.admin.post(reverse("api:book"), {"seat": self.seat.pk, "customer": self.alice_customer.pk}).data["txn_id"]
        for name, args in [
            ("dashboard", []), ("web:movie_list", []), ("web:showtime_list", []),
            ("web:showtime_detail", [showtime.pk]), ("web:booking_list", []), ("web:customer_list", []),
            ("web:customer_detail", [self.alice_customer.pk]), ("web:payment_list", []),
            ("web:transaction_list", []), ("web:transaction_detail", [log_id]), ("web:api_guide", []),
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_customer_pages_and_limits(self):
        self.client.login(username="alice", password="demo12345")
        self.assertEqual(self.client.get(reverse("web:customer_list")).status_code, 403)
        self.assertRedirects(self.client.get(reverse("web:my_wallet")),
                             reverse("web:customer_detail", args=[self.alice_customer.pk]))
        brian = Customer.objects.get(user__username="brian")
        self.assertEqual(self.client.get(reverse("web:customer_detail", args=[brian.pk])).status_code, 403)
