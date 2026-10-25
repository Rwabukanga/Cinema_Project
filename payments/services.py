"""
Server B participant in two-phase commit.

    prepare(...) -> Phase 1: reserve the money (vote YES) or refuse (vote NO)
    commit(...)  -> Phase 2: take the reserved money
    abort(...)   -> Phase 2: give the reserved money back

commit() and abort() are idempotent, so the coordinator can safely repeat them.
"""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Payment, Wallet


def prepare(txn_id, customer_id, amount):
    """Phase 1. Reserve `amount` in the customer's wallet. Returns (vote, message)."""
    with transaction.atomic():
        wallet = Wallet.objects.filter(customer_id=customer_id).first()
        if wallet is None:
            return False, "Customer has no wallet."
        # Atomic check-and-reserve: only succeeds if balance - reserved >= amount.
        reserved = (
            Wallet.objects.filter(pk=wallet.pk, balance__gte=F("reserved") + amount)
            .update(reserved=F("reserved") + amount)
        )
        if reserved == 0:
            return False, "Not enough money in the wallet."
        Payment.objects.create(wallet=wallet, txn_id=txn_id, amount=amount)
    return True, f"{amount} reserved."


def commit(txn_id):
    """Phase 2 (COMMIT). Move the reserved money out of the wallet."""
    with transaction.atomic():
        payment = Payment.objects.filter(txn_id=txn_id, status=Payment.PENDING).first()
        if payment is None:  # already committed (or never prepared): nothing to do
            return
        Wallet.objects.filter(pk=payment.wallet_id).update(
            balance=F("balance") - payment.amount, reserved=F("reserved") - payment.amount
        )
        payment.status = Payment.PAID
        payment.paid_at = timezone.now()
        payment.save()


def abort(txn_id):
    """Phase 2 (ABORT). Release the reserved money."""
    with transaction.atomic():
        payment = Payment.objects.filter(txn_id=txn_id, status=Payment.PENDING).first()
        if payment is None:
            return
        Wallet.objects.filter(pk=payment.wallet_id).update(reserved=F("reserved") - payment.amount)
        payment.status = Payment.ABORTED
        payment.save()


def top_up(customer_id, amount):
    """Add money to a wallet (not part of 2PC)."""
    return Wallet.objects.filter(customer_id=customer_id).update(balance=F("balance") + amount)
