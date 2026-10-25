from django.contrib import admin

from .models import TransactionLog


@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ("txn_id", "state", "seat_vote", "payment_vote", "completed", "created_at")
    list_filter = ("state", "completed")
