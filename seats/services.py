"""
Server A participant in two-phase commit.

The coordinator calls these three functions:
    prepare(...) -> Phase 1: vote YES (seat held) or NO (seat not available)
    commit(...)  -> Phase 2: make the booking final
    abort(...)   -> Phase 2: undo everything done in prepare

commit() and abort() are idempotent: calling them twice is safe. That matters
for recovery, when the coordinator may re-send its decision after a crash.
"""
from django.db import transaction

from .models import Booking, Seat


def prepare(txn_id, seat_id, customer_id):
    """Phase 1. Hold the seat if it is still available. Returns (vote, message)."""
    with transaction.atomic():
        # A conditional UPDATE is atomic: if two customers try the same seat at
        # the same time, only one UPDATE can change it from "available".
        held = (
            Seat.objects.filter(pk=seat_id, status=Seat.AVAILABLE)
            .update(status=Seat.HELD, held_by_txn=txn_id)
        )
        if held == 0:
            return False, "Seat is not available."
        Booking.objects.create(seat_id=seat_id, customer_id=customer_id, txn_id=txn_id, status=Booking.PENDING)
    return True, "Seat held."


def commit(txn_id):
    """Phase 2 (COMMIT). The held seat becomes booked."""
    with transaction.atomic():
        Seat.objects.filter(held_by_txn=txn_id, status=Seat.HELD).update(status=Seat.BOOKED)
        Booking.objects.filter(txn_id=txn_id, status=Booking.PENDING).update(status=Booking.CONFIRMED)


def abort(txn_id):
    """Phase 2 (ABORT). Release the seat and cancel the pending booking."""
    with transaction.atomic():
        Seat.objects.filter(held_by_txn=txn_id, status=Seat.HELD).update(status=Seat.AVAILABLE, held_by_txn=None)
        Booking.objects.filter(txn_id=txn_id, status=Booking.PENDING).update(status=Booking.CANCELLED)
