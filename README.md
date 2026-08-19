# Hotel Booking API

[![CI](https://github.com/diemonBil/HotelBookingAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/diemonBil/HotelBookingAPI/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Django](https://img.shields.io/badge/django-5.2-092E20)
![Tests](https://img.shields.io/badge/tests-103-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)

A REST API for hotel search, room availability, bookings and payments, built with
Django REST Framework.

The interesting part of this project is not CRUD — it is what sits underneath it:
**overlap-aware availability**, **a booking path that cannot double-sell a room under
concurrency**, and **a payment integration behind an interface**, so the whole flow runs
offline in tests and in CI.

```bash
git clone https://github.com/diemonBil/HotelBookingAPI.git
cd HotelBookingAPI
docker compose up --build
```

That is the whole setup. No `.env`, no database, no merchant account: the stack ships a
Postgres service, seeds demo data on first boot and defaults to a fake payment provider.
The API is then at <http://localhost:8000/api/v1/> and the docs at
<http://localhost:8000/api/v1/docs/>.

---

## Contents

- [What it does](#what-it-does)
- [Design notes](#design-notes)
- [Data model](#data-model)
- [API](#api)
- [Running it](#running-it)
- [Configuration](#configuration)
- [Testing](#testing)
- [Payments](#payments)
- [Deployment](#deployment)
- [Project layout](#project-layout)

---

## What it does

- **Public catalogue** — browse hotels, rooms, room types and amenities without an
  account, with filtering, search, ordering and pagination.
- **Availability search** — given a hotel, a date range and a party size, return the room
  types that actually have a free room.
- **Booking** — reserve a room of a chosen type; the API assigns a specific room, prices
  the stay and opens a payment invoice.
- **Payments** — a provider creates the invoice and reports the outcome through a signed
  webhook, which drives the booking between `pending`, `confirmed` and `cancelled`.
- **Reviews** — one review per guest per hotel, publicly readable, editable only by its
  author.
- **Accounts** — JWT authentication with registration, login, refresh and a `/me` profile
  endpoint, rate limited against credential stuffing.

## Design notes

The parts worth reading the code for.

### Availability is one query, not a loop

Whether a room is free is a question about overlapping intervals: two stays overlap when
each starts before the other ends. That is expressed once, in
[`hotel/services.py`](hotel/services.py), and reused by both the availability endpoint and
the booking path:

```python
Booking.objects.exclude(status__in=Booking.RELEASING_STATUSES)
    .filter(check_in__lt=check_out, check_out__gt=check_in)
    .values_list("rooms__id", flat=True)
```

Cancelled bookings drop out of that set, which is what makes a cancellation release its
room. Back-to-back stays — one guest checking out the morning another checks in — are
deliberately *not* an overlap.

### Two guests cannot buy the same room

Checking availability and then creating the booking is a read-then-write, so a check that
passes is not a guarantee by the time the write lands. The booking service re-checks
inside the transaction with the candidate rows locked (`SELECT ... FOR UPDATE`), so
concurrent requests serialise and the loser gets a clean 400 rather than a room sold
twice. The serializer still checks first, but only to produce a good error message — the
binding decision is the locked one.

The external invoice call happens *after* that transaction commits, so a slow acquirer
never holds database locks. If it fails, the booking is cancelled and the room is released.

### Nights are dates

`check_in` and `check_out` are `DateField`, not `DateTimeField`. A hotel night is a
calendar night: a stay from the 1st to the 2nd is one night whatever the clock says. This
also removes a whole class of bug — with timestamps, a 21-hour stay divided into `.days`
is zero nights, and therefore a free room.

### Payments sit behind an interface

`PaymentProvider` in [`hotel/payments/base.py`](hotel/payments/base.py) declares three
operations: create an invoice, verify a webhook, parse a webhook. Two implementations
satisfy it — Monobank, and a fake that runs the same flow with no network. Selecting one is
a `PAYMENT_PROVIDER` environment variable, which is why the test suite exercises the
complete booking-to-confirmation path without mocking HTTP.

### The webhook authenticates itself

Monobank signs each callback with ECDSA over the raw request body. The endpoint verifies
`X-Sign` against the merchant public key before touching the database, and refuses to run
with verification disabled outside `DEBUG`. Applying an event is idempotent, because
providers retry.

## Data model

```mermaid
erDiagram
    USER ||--o{ BOOKING : places
    USER ||--o{ REVIEW : writes
    HOTEL ||--o{ ROOM : has
    HOTEL ||--o{ REVIEW : receives
    HOTEL ||--o{ BOOKING : hosts
    ROOMTYPE ||--o{ ROOM : categorises
    ROOM }o--o{ AMENITY : offers
    ROOM }o--o{ BOOKING : "reserved in"
    BOOKING ||--|| PAYMENT : "settled by"

    USER {
        int id PK
        string username UK
        string email UK
        bool is_staff
    }
    HOTEL {
        int id PK
        string name
        string location
        text description
    }
    ROOMTYPE {
        int id PK
        string name UK
    }
    ROOM {
        int id PK
        int hotel FK
        int room_number
        int room_type FK
        decimal price_per_night
        bool is_available
        int max_guests
    }
    AMENITY {
        int id PK
        string name UK
    }
    BOOKING {
        int id PK
        int user FK
        int hotel FK
        date check_in
        date check_out
        int adults
        int children
        string status
        datetime created_at
    }
    PAYMENT {
        int id PK
        int booking FK
        string provider
        string reference UK
        string provider_invoice_id UK
        decimal amount
        int currency_code
        string status
        url payment_url
        datetime paid_at
    }
    REVIEW {
        int id PK
        int user FK
        int hotel FK
        int rating
        text comment
        datetime created_at
    }
```

Integrity is enforced in the database, not only in serializers: `check_out > check_in`,
at least one adult, one room number per hotel, one review per guest per hotel, and a
unique payment reference.

## API

All routes are under `/api/v1/`.

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/user/register/` | public | Create an account |
| `POST` | `/user/login/` | public | Obtain an access/refresh token pair |
| `POST` | `/user/token/refresh/` | public | Refresh an access token |
| `GET` `PUT` `PATCH` | `/user/me/` | authenticated | Read or update own profile |
| `GET` | `/hotels/` `/rooms/` `/room-types/` `/amenities/` | public | Browse the catalogue |
| `POST` `PUT` `DELETE` | `/hotels/` `/rooms/` … | staff | Manage the catalogue |
| `GET` | `/availability/room-types/` | public | Room types free for a date range |
| `GET` | `/bookings/` | authenticated | Own bookings (staff see all) |
| `POST` | `/bookings/` | authenticated | Create a booking and get a payment link |
| `POST` | `/bookings/{id}/cancel/` | owner or staff | Cancel and release the room |
| `GET` | `/reviews/` | public | Read reviews |
| `POST` `PATCH` `DELETE` | `/reviews/` | author or staff | Manage own reviews |
| `GET` | `/payments/` | staff | Payment records |
| `POST` | `/payments/webhook/` | provider signature | Payment status callback |
| `GET` | `/health/` | public | Liveness and database probe |
| `GET` | `/docs/` `/redoc/` `/schema/` | public | OpenAPI 3 documentation |

### A booking, end to end

```bash
# 1. Log in
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/user/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username": "guest1", "password": "DemoPassw0rd!42"}' | jq -r .access)
```

```bash
# 2. Find out what is free
curl -s -G http://localhost:8000/api/v1/availability/room-types/ \
  -d hotel=1 -d check_in=2026-09-01 -d check_out=2026-09-04 -d adults=2 | jq
```

```bash
# 3. Book it — the response carries the payment link
curl -s -X POST http://localhost:8000/api/v1/bookings/ \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"hotel": 1, "room_type": 2, "check_in": "2026-09-01",
       "check_out": "2026-09-04", "adults": 2, "children": 0}' | jq
```

```json
{
  "id": 5,
  "hotel_name": "Seaside Grand",
  "check_in": "2026-09-01",
  "check_out": "2026-09-04",
  "nights": 3,
  "status": "pending",
  "rooms": [{ "id": 3, "room_number": 103, "room_type_name": "Double" }],
  "payment": {
    "status": "pending",
    "amount": "255.00",
    "payment_url": "http://localhost:8000/api/v1/payments/success/?invoice=fake_9c1f..."
  }
}
```

The booking becomes `confirmed` when the provider's webhook reports a successful payment.

## Running it

### With Docker (recommended)

```bash
docker compose up --build
```

Seeds four hotels, forty rooms, demo bookings and the accounts `admin`, `guest1`,
`guest2` (password `DemoPassw0rd!42`). Set `SEED_DEMO_DATA=false` to skip that.

### Without Docker

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

With no `DATABASE_URL` set, the project falls back to a local SQLite file, so this works
with nothing else installed.

A `Makefile` wraps the common tasks — `make test`, `make lint`, `make seed`, `make up`.

## Configuration

Every setting comes from the environment; [`.env.example`](.env.example) documents all of
them. The ones that matter:

| Variable | Default | Notes |
| --- | --- | --- |
| `DEBUG` | `False` | Turning it off activates HTTPS redirects, HSTS and secure cookies |
| `DJANGO_SECRET_KEY` | — | Required when `DEBUG=False`; startup fails loudly without it |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated |
| `DATABASE_URL` | SQLite file | e.g. `postgres://user:pass@host:5432/db` |
| `PAYMENT_PROVIDER` | `fake` | `fake` or `monobank` |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Where the provider sends redirects and webhooks |
| `MONOBANK_TOKEN` | — | Required only for `PAYMENT_PROVIDER=monobank` |
| `THROTTLE_ANON` / `THROTTLE_USER` / `THROTTLE_AUTH` | `60/min` / `300/min` / `10/min` | DRF rate strings |

## Testing

```bash
pytest                                   # 101 tests on SQLite, ~2s
pytest --cov --cov-report=term           # coverage report
```

Two tests need real concurrent transactions and are skipped on SQLite. To run
the full 103 against PostgreSQL:

```bash
TEST_DATABASE_URL=postgres://user:pass@host:5432/db pytest
```

Coverage sits at **94%**, and the suite is written around behaviour rather than
implementation. It covers, among other things:

- overlapping, adjacent and cancelled stays;
- the last room of a type being claimed twice, both sequentially and by two
  genuinely parallel transactions;
- a provider outage leaving no room held;
- forged and unsigned payment webhooks being rejected, and replayed ones being ignored;
- one user being unable to edit another's review;
- malformed availability queries returning `400` rather than `500`;
- list endpoints not issuing a query per row.

Tests run against `HotelBookingAPI/settings_test.py`, so a local `.env` cannot change what
CI verifies. CI runs the suite twice — once on SQLite, once on PostgreSQL — and also checks
formatting, missing migrations, `manage.py check --deploy`, that migrations apply to real
PostgreSQL, that the OpenAPI schema builds without warnings, and that the Docker stack boots
and answers on `/health/`.

## Payments

`PAYMENT_PROVIDER=fake` is the default and needs nothing. To use the real Monobank
acquiring API you need a merchant token and a publicly reachable URL:

```env
PAYMENT_PROVIDER=monobank
MONOBANK_TOKEN=your-merchant-token
PUBLIC_BASE_URL=https://your-public-host
```

Monobank then calls `POST {PUBLIC_BASE_URL}/api/v1/payments/webhook/` with an `X-Sign`
header; the request is rejected unless that signature verifies against the merchant public
key. For local experiments, expose the port with a tunnel and point `PUBLIC_BASE_URL` at it.

## Deployment

The repository ships a [Render](https://render.com) blueprint, so a deployment needs no
manual configuration:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/diemonBil/HotelBookingAPI)

Or from the dashboard: **New → Blueprint → pick this repository**. Render reads
[`render.yaml`](render.yaml), builds the Docker image, generates `DJANGO_SECRET_KEY`, runs
migrations and seeds the demo data on first boot. The only value to supply is
`DATABASE_URL`; the app derives the rest from the platform:

| Concern | How it is handled |
| --- | --- |
| Database | External Postgres via `DATABASE_URL` (Neon) |
| Port | `gunicorn.conf.py` binds `$PORT` |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `PUBLIC_BASE_URL` | Derived from `RENDER_EXTERNAL_HOSTNAME` |
| HTTPS | `SECURE_SSL_REDIRECT` with `X-Forwarded-Proto`; `/health/` is exempt so the platform probe is not redirected |
| Health check | `healthCheckPath: /api/v1/health/` |
| Static files | Collected into the image at build time, served by WhiteNoise |

The database is deliberately **not** Render's: its free PostgreSQL is deleted after 30
days. The blueprint expects `DATABASE_URL` to point at a free permanent host such as
[Neon](https://neon.tech), entered once in the Render dashboard. One caveat remains on the
free web tier: the instance sleeps after ~15 minutes idle, so the first request afterwards
takes roughly a minute.

To take real payments, set `PAYMENT_PROVIDER=monobank` and `MONOBANK_TOKEN` in the Render
dashboard; `PUBLIC_BASE_URL` is already correct, so the webhook URL resolves by itself.

## Project layout

```
HotelBookingAPI/      Django project: settings, URLs, test settings
hotel/
├── models.py         Hotels, rooms, bookings, payments, reviews
├── services.py       Availability, transactional booking, webhook handling
├── serializers.py    Validation and representation
├── views.py          Thin viewsets and endpoints
├── permissions.py    Read-only-for-guests, owner-only-for-writes
├── payments/         Provider interface + Monobank and fake implementations
├── management/       seed_demo_data command
└── tests/            Test suite
user/                 Custom user model, JWT auth, profile endpoint
Dockerfile            Production image; entrypoint.sh migrates, then serves
docker-compose.yml    Local stack: API + PostgreSQL
render.yaml           Render blueprint: web service + managed database
```
