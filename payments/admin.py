from django.contrib import admin

from .models import Customer, Payment, Wallet


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("customer", "balance", "reserved")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "wallet", "amount", "status", "txn_id", "paid_at")
    list_filter = ("status",)
