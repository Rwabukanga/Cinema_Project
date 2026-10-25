"""
Settings for CineSync, the Distributed Cinema Ticket Booking System.

Everything is stored in Django's DEFAULT database (db.sqlite3).
The three "servers" of the distributed design are three Django apps:

    seats        -> Server A  (Movie, Showtime, Seat, Booking)
    payments     -> Server B  (Customer, Wallet, Payment)
    coordinator  -> Coordinator (TransactionLog + two-phase commit)

Other apps:
    api       -> the REST API (Django REST Framework). Every page gets its data here.
    accounts  -> sign up, log in, log out
    web       -> the AdminLTE pages (HTML shells that call the API with JavaScript)
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Development settings only. Change SECRET_KEY and DEBUG before deploying anywhere.
SECRET_KEY = "django-insecure-change-me-cinesync-demo"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # The distributed design (one app per "server")
    "seats",
    "payments",
    "coordinator",
    # API, accounts and pages
    "api",
    "accounts",
    "web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",   # language switcher in the navbar
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "cinema_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.context_processors.navbar",
            ],
        },
    },
]

WSGI_APPLICATION = "cinema_project.wsgi.application"

# Django's default database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---- Log in / log out ----
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# ---- REST API ----
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",  # the web pages (logged-in browser)
        "rest_framework.authentication.BasicAuthentication",    # tools such as Postman or curl
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": None,
}

# Money every new account starts with (so a new user can book right away)
SIGNUP_STARTING_BALANCE = "200.00"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("fr", "Français")]
TIME_ZONE = "Africa/Johannesburg"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
