from django.contrib import admin
from django.urls import include, path

from web.views import DashboardView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),   # {% url 'set_language' %}
    path("api/", include("api.urls")),                 # REST API  (namespace "api")
    path("accounts/", include("accounts.urls")),       # signup / login / logout
    path("", DashboardView.as_view(), name="dashboard"),
    path("", include("web.urls")),                     # AdminLTE pages (namespace "web")
]
