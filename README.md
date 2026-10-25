# Cinema_Project

A cinema ticket booking system that uses **two-phase commit (2PC)** so a seat is never booked without being paid for, and money is never taken without a seat.

- **Back end:** Django 5 + Django REST Framework. **Every view is an API endpoint.**
- **Front end:** AdminLTE 4 pages that load all their data from the API with JavaScript.
- **Accounts:** Sign-up and Login pages. Every new user gets a customer wallet.
- **Database:** Django's default database (`db.sqlite3`).

```
REST API  /api/...            (api app: serializers + viewsets)
        │
        ├── seats        "Server A"    Movie, Showtime, Seat, Booking        prepare / commit / abort
        ├── payments     "Server B"    Customer, Wallet, Payment             prepare / commit / abort
        └── coordinator  "Coordinator" TransactionLog + book_ticket() + recover()
                                   all in ONE database: db.sqlite3
```

---

## Part 1: Run it

```bash
# 1. Virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
source venv/bin/activate         # macOS / Linux

# 2. Install
pip install -r requirements.txt

# 3. Database + demo data
python manage.py migrate
python manage.py seed_data

# 4. Start
python manage.py runserver
```

Open **http://127.0.0.1:8000/**. You'll land on the login page.

| Login | Password | Role |
|---|---|---|
| `admin` | `admin12345` | Staff: sees everything, adds movies/showtimes/customers, runs recovery |
| `alice` | `demo12345` | Customer with 300.00 |
| `brian` | `demo12345` | Customer with 150.00 |
| `chloe` | `demo12345` | Customer with 40.00 (too little for a ticket, so the booking aborts) |

You can also click **Create an account** on the login page. A new account starts with 200.00.

Run the tests (26 tests): `python manage.py test`

> The demo passwords are for the demo only. Change them (and `SECRET_KEY`, `DEBUG`) before putting the site anywhere public.

---

## Part 2: How it was built, step by step

### Step 1. Create the project and the apps

```bash
pip install django djangorestframework
django-admin startproject cinema_project .
python manage.py startapp seats        # Server A
python manage.py startapp payments     # Server B
python manage.py startapp coordinator  # two-phase commit
python manage.py startapp api          # REST API
python manage.py startapp accounts     # sign up / log in
python manage.py startapp web          # AdminLTE pages
```

### Step 2. Settings (`cinema_project/settings.py`)

- Add `rest_framework` and the six apps to `INSTALLED_APPS`.
- Keep Django's **default database**:
  ```python
  DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
  ```
- Configure the API: logged-in users only, session login for the pages, Basic auth for Postman/curl, no paging (DataTables pages in the browser):
  ```python
  REST_FRAMEWORK = {
      "DEFAULT_AUTHENTICATION_CLASSES": [
          "rest_framework.authentication.SessionAuthentication",
          "rest_framework.authentication.BasicAuthentication",
      ],
      "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
      "DEFAULT_PAGINATION_CLASS": None,
  }
  ```
- Log in / out: `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "dashboard"`, `LOGOUT_REDIRECT_URL = "login"`.
- Add the context processor `web.context_processors.navbar` (fills the navbar bell, badges and sidebar counter).

### Step 3. Models (they follow the ERD)

| App | Models | Notes |
|---|---|---|
| `seats/models.py` | Movie, Showtime, Seat, Booking | Seat status `available → held → booked`. `Booking.customer_id` is a plain number, because the customer "lives" on Server B. |
| `payments/models.py` | Customer, Wallet, Payment | `Customer.user` links a login to a customer. `Wallet.reserved` is money held during Phase 1. |
| `coordinator/models.py` | TransactionLog | `started / prepared / committed / aborted`, the two votes, and `completed`. |

```bash
python manage.py makemigrations seats payments coordinator
python manage.py migrate
```

### Step 4. Two-phase commit (the business logic)

- `seats/services.py` and `payments/services.py`: each "server" has `prepare()`, `commit()` and `abort()`.
- `coordinator/services.py`:
  ```python
  def book_ticket(customer_id, seat_id, scenario="none"):
      log = begin_transaction(customer_id, seat_id)      # STARTED
      if send_prepare(log, scenario):                     # Phase 1: both vote YES?
          log.state = "committed"; log.save()             # decision written FIRST
          send_commit(log)                                # Phase 2
      else:
          log.state = "aborted"; log.save()
          send_abort(log)
      return log
  ```
  `recover()` finishes open transactions: a logged COMMIT is sent again, and anything without a decision is aborted.

### Step 5. The REST API (`api/`)

- **`api/serializers.py`** turns each model into JSON. It adds useful fields, for example `occupancy` on a showtime and `available` on a customer. Creating a showtime also creates its seats from `rows` and `seats_per_row`.
- **`api/permissions.py`**: `IsStaffOrReadOnly` (everyone reads, staff writes) and `IsStaff`.
- **`api/views.py`** has one ViewSet per model, plus three extra API views:

| Endpoint | Methods | Notes |
|---|---|---|
| `/api/movies/` | GET, POST, PUT, PATCH, DELETE | staff writes; delete refused if confirmed bookings |
| `/api/showtimes/` · `/api/showtimes/<id>/seats/` | GET, POST, PUT, PATCH, DELETE | `?movie=ID`; seats created automatically |
| `/api/seats/` | GET | `?showtime=ID` |
| `/api/bookings/` | GET | customers see only their own |
| `/api/customers/` · `/api/customers/<id>/top-up/` | GET, POST, PATCH, DELETE · POST | staff manages; customers see/top up themselves |
| `/api/payments/` | GET | customers see only their own |
| `/api/transactions/` · `/api/transactions/recover/` | GET · POST | recovery is staff only |
| `/api/book/` | POST | `{"seat": 12, "scenario": "none"}`, which runs 2PC |
| `/api/dashboard/` | GET | every number on the dashboard |
| `/api/me/` | GET | the logged-in user and their wallet |

- **`api/urls.py`** registers the ViewSets with a `DefaultRouter`, so `/api/` shows DRF's browsable API.

Bookings and payments are **read-only** in the API on purpose: the only way to create them is `POST /api/book/`, which runs two-phase commit.

### Step 6. Sign up and log in (`accounts/`)

- **`accounts/forms.py`**: `SignUpForm` creates the **User**, a linked **Customer** and a **Wallet** (starting balance 200.00) in one database transaction.
- **`accounts/views.py`**: `SignUpView` (logs the new user in straight away) and `SignInView` (with "Remember me").
- **`accounts/urls.py`**: `/accounts/login/`, `/accounts/signup/`, `/accounts/logout/` (POST).
- Templates: `templates/accounts/auth_base.html`, `templates/registration/login.html`, `templates/accounts/signup.html` (AdminLTE login-box / register-box).

### Step 7. The AdminLTE layout

- `templates/base.html` is your layout, with these changes:
  - **DataTables is loaded once (3.1.3).** The old file loaded 2.1.8 *and* 3.1.3. Version 2 needs jQuery, which the page doesn't load.
  - It adds `<div id="api-alerts">` for API messages and loads `static/js/app.js`.
  - It has a `breadcrumb_parent` block, and the CineSync title and footer.
- `templates/navbar.html`: the latest bookings, notifications from the coordinator, language, full screen, dark mode, and the user menu (My wallet, Sign out).
- `templates/sidebar.html`: menus for Server A, Server B and the Coordinator, plus REST API and Admin Site. It shows a red badge when transactions need recovery.

### Step 8. The JavaScript that talks to the API (`static/js/app.js`)

```js
Cine.Api.get(url) / post(url, data) / put / patch / del   // fetch() + CSRF token + JSON
Cine.apiTable(table, {url, columns})                      // a DataTable filled from the API
Cine.apiForm(form, {onSuccess})                           // a form that sends JSON; shows field errors
Cine.notify(message, type)                                // AdminLTE alert
```

### Step 9. The pages (`web/`)

`web/views.py` only returns the page shells (`LoginRequiredMixin` + `TemplateView`). Each template asks the API for its data:

| Page | URL | Uses |
|---|---|---|
| Dashboard | `/` | `GET /api/dashboard/` |
| Movies | `/cinema/movies/` | `/api/movies/` (add/edit/delete in a modal) |
| Showtimes | `/cinema/showtimes/` | `/api/showtimes/` (add/edit/delete in a modal) |
| Seat map + booking | `/cinema/showtimes/<id>/` | `/api/showtimes/<id>/seats/`, `POST /api/book/` |
| Bookings | `/cinema/bookings/` | `/api/bookings/` |
| Customers & wallets (staff) | `/payments/customers/` | `/api/customers/` + top-up |
| My wallet / customer page | `/payments/customers/<id>/` | `/api/customers/<id>/`, payments, bookings |
| Payments | `/payments/` | `/api/payments/` |
| Transaction log | `/transactions/` | `/api/transactions/`, `POST /api/transactions/recover/` |
| Transaction details | `/transactions/<uuid>/` | `/api/transactions/<uuid>/` |
| REST API guide | `/api-guide/` | every endpoint, with links |

### Step 10. Demo data and tests

- `python manage.py seed_data`: movies, showtimes, seats, customers, and the demo logins.
- `python manage.py recover_transactions`: recovery from the terminal.
- `coordinator/tests.py`: the 2PC rules. `api/tests.py`: API permissions, booking, recovery, top-up, sign-up, login and every page.

---

## Part 3: Demo script for the presentation

1. **Sign up** as a new user. The dashboard shows a wallet of 200.00.
2. **Showtimes → Seats**: pick a seat and click **Book ticket**. It's **COMMITTED**: both servers voted YES.
3. Log in as **admin**, book for **Chloe**. It's **ABORTED**: Server B voted NO (not enough money), so Server A released the seat.
4. Book with scenario **Payment server is down**. It's **ABORTED** (a timeout counts as NO).
5. Book with scenario **Coordinator crashes before deciding**. It's **PREPARED**: the seat is yellow (held) and the money is reserved. The dashboard blinks red. *This is why 2PC is called blocking.*
6. **Transaction Log → Run recovery**. The transaction is aborted, and the seat and the money are released.

---

## Notes

- **CDN files:** AdminLTE, Bootstrap, Bootstrap Icons, DataTables and Chart.js load from CDNs, so the browser needs internet access.
- **PostgreSQL** (optional): `pip install "psycopg[binary]"`, then set `DATABASES["default"]` to `ENGINE "django.db.backends.postgresql"` with `NAME`, `USER`, `PASSWORD`, `HOST` and `PORT`, and run `migrate` again.
