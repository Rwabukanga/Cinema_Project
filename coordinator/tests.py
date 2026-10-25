"""Two-phase commit rules.   Run:  python manage.py test"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from payments.models import Customer, Payment, Wallet
from seats.models import Booking, Seat

from .models import TransactionLog
from .services import SimulatedCrash, book_ticket, recover


class TwoPhaseCommitTests(TestCase):
    def setUp(self):
        call_command("seed_data", stdout=StringIO())
        self.alice = Customer.objects.get(email="alice@example.com")   # 300
        self.brian = Customer.objects.get(email="brian@example.com")   # 150
        self.chloe = Customer.objects.get(email="chloe@example.com")   # 40
        self.seat = Seat.objects.filter(showtime__ticket_price=Decimal("75.00")).first()

    def wallet(self, customer):
        return Wallet.objects.get(customer=customer)

    def test_successful_booking_commits_on_both_servers(self):
        log = book_ticket(self.alice.pk, self.seat.pk)
        self.seat.refresh_from_db()
        self.assertEqual(log.state, TransactionLog.COMMITTED)
        self.assertTrue(log.completed)
        self.assertEqual(self.seat.status, Seat.BOOKED)
        self.assertEqual(Booking.objects.get(txn_id=log.txn_id).status, Booking.CONFIRMED)
        self.assertEqual(Payment.objects.get(txn_id=log.txn_id).status, Payment.PAID)
        self.assertEqual(self.wallet(self.alice).balance, Decimal("225.00"))
        self.assertEqual(self.wallet(self.alice).reserved, Decimal("0"))

    def test_not_enough_money_aborts_and_releases_the_seat(self):
        log = book_ticket(self.chloe.pk, self.seat.pk)
        self.seat.refresh_from_db()
        self.assertEqual(log.state, TransactionLog.ABORTED)
        self.assertTrue(log.seat_vote)
        self.assertFalse(log.payment_vote)
        self.assertEqual(self.seat.status, Seat.AVAILABLE)
        self.assertEqual(Booking.objects.get(txn_id=log.txn_id).status, Booking.CANCELLED)
        self.assertEqual(self.wallet(self.chloe).balance, Decimal("40.00"))

    def test_seat_already_taken_aborts_and_releases_the_money(self):
        book_ticket(self.alice.pk, self.seat.pk)
        log = book_ticket(self.brian.pk, self.seat.pk)
        self.assertEqual(log.state, TransactionLog.ABORTED)
        self.assertFalse(log.seat_vote)
        self.assertEqual(self.wallet(self.brian).reserved, Decimal("0"))
        self.assertEqual(Payment.objects.get(txn_id=log.txn_id).status, Payment.ABORTED)

    def test_payment_server_down_aborts(self):
        log = book_ticket(self.alice.pk, self.seat.pk, scenario="payment_server_down")
        self.seat.refresh_from_db()
        self.assertEqual(log.state, TransactionLog.ABORTED)
        self.assertEqual(self.seat.status, Seat.AVAILABLE)
        self.assertFalse(Payment.objects.filter(txn_id=log.txn_id).exists())

    def test_coordinator_crash_blocks_until_recovery(self):
        with self.assertRaises(SimulatedCrash):
            book_ticket(self.alice.pk, self.seat.pk, scenario="coordinator_crash")
        log = TransactionLog.objects.get()
        self.seat.refresh_from_db()
        self.assertEqual(log.state, TransactionLog.PREPARED)
        self.assertEqual(self.seat.status, Seat.HELD)
        self.assertEqual(self.wallet(self.alice).reserved, Decimal("75.00"))

        self.assertEqual(recover(), [(log.txn_id, "aborted")])
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, Seat.AVAILABLE)
        self.assertEqual(self.wallet(self.alice).reserved, Decimal("0"))

    def test_recovery_resends_a_logged_commit_only_once(self):
        log = book_ticket(self.alice.pk, self.seat.pk)
        Seat.objects.filter(pk=self.seat.pk).update(status=Seat.HELD)
        Booking.objects.filter(txn_id=log.txn_id).update(status=Booking.PENDING)
        TransactionLog.objects.filter(pk=log.pk).update(completed=False)
        self.assertEqual(recover(), [(log.txn_id, "commit re-sent")])
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, Seat.BOOKED)
        self.assertEqual(self.wallet(self.alice).balance, Decimal("225.00"))   # not charged twice

    def test_money_is_never_created_or_lost(self):
        before = sum(w.balance for w in Wallet.objects.all())
        seats = list(Seat.objects.filter(showtime__ticket_price=Decimal("60.00"))[:3])
        book_ticket(self.alice.pk, seats[0].pk)
        book_ticket(self.chloe.pk, seats[1].pk)   # aborts: not enough money
        book_ticket(self.brian.pk, seats[0].pk)   # aborts: seat taken
        book_ticket(self.brian.pk, seats[2].pk)
        paid = sum(p.amount for p in Payment.objects.filter(status=Payment.PAID))
        after = sum(w.balance for w in Wallet.objects.all())
        self.assertEqual(before, after + paid)
