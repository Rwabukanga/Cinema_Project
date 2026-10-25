"""Server B: Customer, Wallet, Payment."""
from django.conf import settings
from django.db import models


class Customer(models.Model):
    # The login account of this customer (empty for customers created by staff)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="customer"
    )
    full_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.full_name


class Wallet(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Money put aside during Phase 1 (prepare). It cannot be spent twice.
    reserved = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def available(self):
        return self.balance - self.reserved

    def __str__(self):
        return f"Wallet of {self.customer} ({self.balance})"


class Payment(models.Model):
    PENDING = "pending"    # amount reserved in Phase 1
    PAID = "paid"          # after global COMMIT
    ABORTED = "aborted"    # after global ABORT
    STATUS_CHOICES = [(PENDING, "Pending"), (PAID, "Paid"), (ABORTED, "Aborted")]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="payments")
    txn_id = models.UUIDField(unique=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment {self.pk}: {self.amount} ({self.status})"
