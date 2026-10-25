from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "api"

router = DefaultRouter()
router.register("movies", views.MovieViewSet, basename="movie")
router.register("showtimes", views.ShowtimeViewSet, basename="showtime")
router.register("seats", views.SeatViewSet, basename="seat")
router.register("bookings", views.BookingViewSet, basename="booking")
router.register("customers", views.CustomerViewSet, basename="customer")
router.register("payments", views.PaymentViewSet, basename="payment")
router.register("transactions", views.TransactionViewSet, basename="transaction")

urlpatterns = [
    path("book/", views.BookTicketView.as_view(), name="book"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("me/", views.MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
