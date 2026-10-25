from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    # Server A: cinema
    path("cinema/movies/", views.MovieListView.as_view(), name="movie_list"),
    path("cinema/showtimes/", views.ShowtimeListView.as_view(), name="showtime_list"),
    path("cinema/showtimes/<int:pk>/", views.ShowtimeDetailView.as_view(), name="showtime_detail"),
    path("cinema/bookings/", views.BookingListView.as_view(), name="booking_list"),
    # Server B: payments
    path("payments/customers/", views.CustomerListView.as_view(), name="customer_list"),
    path("payments/customers/<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("payments/my-wallet/", views.MyWalletView.as_view(), name="my_wallet"),
    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    # Coordinator
    path("transactions/", views.TransactionListView.as_view(), name="transaction_list"),
    path("transactions/<uuid:pk>/", views.TransactionDetailView.as_view(), name="transaction_detail"),
    # API guide
    path("api-guide/", views.ApiGuideView.as_view(), name="api_guide"),
]
