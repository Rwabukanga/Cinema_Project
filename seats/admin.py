from django.contrib import admin

from .models import Booking, Movie, Seat, Showtime


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "genre", "duration_min")


@admin.register(Showtime)
class ShowtimeAdmin(admin.ModelAdmin):
    list_display = ("movie", "hall", "start_time", "ticket_price")


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("seat_no", "showtime", "status", "held_by_txn")
    list_filter = ("status", "showtime")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "seat", "customer_id", "status", "txn_id", "booked_at")
    list_filter = ("status",)
