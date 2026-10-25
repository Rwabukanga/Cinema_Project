"""Coordinator database: the TransactionLog (the coordinator's write-ahead log)."""
import uuid

from django.db import models


class TransactionLog(models.Model):
    STARTED = "started"      # Phase 1 running: asking participants to prepare
    PREPARED = "prepared"    # every participant voted YES, decision not written yet
    COMMITTED = "committed"  # decision = COMMIT (written BEFORE telling participants)
    ABORTED = "aborted"      # decision = ABORT
    STATE_CHOICES = [
        (STARTED, "Started"),
        (PREPARED, "Prepared"),
        (COMMITTED, "Committed"),
        (ABORTED, "Aborted"),
    ]

    txn_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state = models.CharField(max_length=12, choices=STATE_CHOICES, default=STARTED)
    # What the transaction is about (plain numbers: the rows live on other servers)
    customer_id = models.IntegerField()
    seat_id = models.IntegerField()
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    # Votes collected in Phase 1 (None = no answer yet)
    seat_vote = models.BooleanField(null=True)
    payment_vote = models.BooleanField(null=True)
    # True once every participant has been told the final decision (end of Phase 2)
    completed = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.txn_id} ({self.state})"
