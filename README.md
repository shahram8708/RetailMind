# RetailMind 🏬

### Make Your Mall as Smart as the Best Digital Platform

**RetailMind** is an AI-powered operations platform for mall teams, staff, and shoppers — deploying autonomous agents that handle inventory risk scoring, campaign generation, facility monitoring, and shopper assistance in real time, with full offline reliability as a Progressive Web App.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-black?logo=flask)](https://flask.palletsprojects.com/)
[![Gemini AI](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4?logo=google)](https://ai.google.dev/)
[![License](https://img.shields.io/badge/License-Not_Specified-lightgrey)](#license)
[![PWA](https://img.shields.io/badge/PWA-Enabled-5A0FC8?logo=googlechrome)](https://web.dev/progressive-web-apps/)
[![Tests](https://img.shields.io/badge/Tests-pytest-green?logo=pytest)](https://pytest.org/)
[![Last Commit](https://img.shields.io/badge/Last_Commit-May_2026-brightgreen)](https://github.com/shahram8708/RetailMind)

---

## Table of Contents

1. [About the Project](#about-the-project)
2. [Key Features](#key-features)
3. [Tech Stack](#tech-stack)
4. [Project Structure](#project-structure)
5. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Installation](#installation)
   - [Environment Variables](#environment-variables)
   - [Running the Project](#running-the-project)
6. [Usage](#usage)
7. [API Documentation](#api-documentation)
8. [Configuration](#configuration)
9. [Testing](#testing)
10. [Deployment](#deployment)
11. [Contributing](#contributing)
12. [Roadmap](#roadmap)
13. [License](#license)
14. [Acknowledgements](#acknowledgements)
15. [Contact / Author](#contact--author)

---

## About the Project

Retail malls generate enormous amounts of operational data every minute — foot traffic by zone, sales velocity per SKU, equipment sensor readings, campaign impressions — and nearly all of it goes unprocessed until something breaks. RetailMind exists to change that.

It gives mall operators and their teams a single intelligent platform where AI agents work in the background: flagging stock that is about to run out before it does, drafting marketing campaigns anchored to real-time weather and foot traffic, raising maintenance work orders the moment a sensor reading goes anomalous, and answering shopper queries via a natural-language search interface.

RetailMind is built for **Indian mall operators** — pricing is in INR, payments go through Razorpay, and the platform ships with multi-tier subscription management (Starter, Professional, Enterprise) and a full superadmin console for the platform operator. It also ships as a fully functional Progressive Web App, meaning staff can keep working even when the internet drops.

---

## Key Features

**Autonomous AI Agent with Four Missions** — a background agent continuously runs inventory, campaign, facility, and shopper missions on a configurable schedule, surfacing actions for human approval or executing them automatically based on per-property thresholds.

**Stock Risk Scoring (SRS)** — every SKU is scored on a 0–1 scale using sales velocity, reorder thresholds, supplier lead times, and SKU criticality; Gemini 2.5 Flash writes the human-readable reasoning for every alert.

**Campaign Opportunity Scoring (COS)** — the agent evaluates foot traffic patterns, seasonal factors, and real-time weather context (also queried via Gemini) to surface and auto-generate targeted campaign copy for the right store, zone, and audience.

**Facility Performance Scoring (FPS)** — sensor readings from HVAC, escalators, elevators, and other equipment are compared with historical baselines using Z-score anomaly detection; critical scores automatically raise work orders.

**AI-Powered Shopper Search** — shoppers can describe what they are looking for in plain language; Gemini extracts structured intent (category, brand, price range, size, color) and ranks matching SKUs across all tenants in the mall.

**Progressive Web App with Offline Support** — a Service Worker pre-caches all critical routes and assets; an IndexedDB-backed sync queue replays mutations made while offline once connectivity is restored.

**Web Push Notifications** — VAPID-based push notifications deliver real-time alerts to subscribed staff browsers, backed by the `pywebpush` library.

**Built-in Billing with Razorpay** — subscription management, order creation, payment signature verification, and receipt email dispatch are wired end-to-end; the billing history page renders downloadable invoice pages.

**PDF Analytics Export** — the analytics module can generate a full property performance report as a PDF (via ReportLab) covering revenue trends, campaign ROI, foot traffic, and agent activity.

**Elasticsearch-Accelerated Search** — when Elasticsearch credentials are present, shopper search and inventory queries are routed through an ES index; if not, the platform falls back gracefully to SQLite/PostgreSQL queries.

**5-Step Guided Onboarding** — new mall admins walk through property setup, tenant configuration, inventory upload, team invitations, and agent configuration in a gated multi-step wizard before gaining dashboard access.

**Superadmin Platform Console** — a completely separate admin surface lets platform operators manage all properties, tenants, users, subscriptions, billing records, demo requests, agent logs, and system health in one place.

**Role-Based Access Control** — six distinct roles (`superadmin`, `mall_admin`, `store_manager`, `marketing_manager`, `facility_manager`, `shopper`) each route to an appropriate dashboard and see only the actions permitted by the `@role_required` decorator.

---

## Tech Stack

**Backend**

| Tool | Purpose |
|---|---|
| Python 3.9+ | Runtime |
| Flask | Web framework and blueprint routing |
| Flask-SQLAlchemy | ORM |
| Flask-Migrate / Alembic | Database migrations |
| Flask-Login | Session-based authentication |
| Flask-WTF / WTForms | Forms with CSRF protection |
| Flask-Bcrypt | Password hashing |
| Flask-Mail | Transactional email via SMTP |
| Flask-Caching | SimpleCache for performance |
| Flask-Limiter | Rate limiting (200/day, 50/hour default) |
| APScheduler | Background job scheduler (BackgroundScheduler) |
| Google GenAI (`google-genai`) | Gemini 2.5 Flash for reasoning, copy, and intent extraction |
| Razorpay | Payment gateway (INR) |
| Elasticsearch | Optional search acceleration |
| ReportLab | PDF report generation |
| WeasyPrint | HTML-to-PDF rendering |
| pywebpush | Web Push / VAPID notifications |
| Pillow | Image handling |
| Gunicorn | Production WSGI server |
| python-dotenv | `.env` file loading |

**Frontend**

| Tool | Purpose |
|---|---|
| Jinja2 | Server-side HTML templating |
| Bootstrap 5.3.3 | UI component library (CDN) |
| Chart.js 4.4.3 | Dashboard and analytics charts (CDN) |
| Vanilla JavaScript | All page-level interactivity |
| Service Worker (`sw.js`) | PWA offline caching and background sync |
| IndexedDB (`idb-service.js`) | Client-side storage for offline queue |

**Database**

| Option | Notes |
|---|---|
| SQLite | Default (zero-config for development) |
| PostgreSQL | Recommended for production (set `DATABASE_URL`) |

**DevOps / Other**

| Tool | Purpose |
|---|---|
| pytest | Test runner |
| `unittest` | Test base classes |
| `.env` / `python-dotenv` | Environment-based configuration |
| `wsgi.py` | Production entry point for Gunicorn |

---

## Project Structure

```
RetailMind-main/
│
├── run.py                         # Development server entry point
├── wsgi.py                        # Production WSGI entry point (Gunicorn)
├── requirements.txt               # All Python dependencies
├── .env.example                   # Template for all required environment variables
├── .gitignore                     # Standard Python + Flask ignores
│
├── app/                           # Main Flask application package
│   ├── __init__.py                # App factory (create_app), blueprint registration, CSP headers
│   ├── config.py                  # DevelopmentConfig, ProductionConfig, TestingConfig
│   ├── extensions.py              # Flask extension instances (db, login_manager, mail, etc.)
│   ├── seed.py                    # Database seeder — populates demo property, tenants, inventory, agents
│   │
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── user.py                # User, EmailVerificationToken, PasswordResetToken
│   │   ├── property.py            # MallProperty — the top-level entity for each mall
│   │   ├── tenant.py              # Tenant — individual stores inside a property
│   │   ├── inventory.py           # InventoryItem, SalesVelocity, FootTraffic
│   │   ├── campaign.py            # Campaign — AI-generated or manual marketing campaigns
│   │   ├── facility.py            # Equipment, SensorReading, WorkOrder
│   │   ├── agent.py               # AgentConfiguration, AgentAction
│   │   ├── billing.py             # Subscription, PaymentRecord, DemoRequest
│   │   ├── notification.py        # Notification, PushSubscription
│   │   └── shopper.py             # ShopperInteraction — query logs for the shopper portal
│   │
│   ├── routes/                    # Flask blueprints — one per feature domain
│   │   ├── public.py              # Landing, features, pricing, about, demo request
│   │   ├── auth.py                # Register, login, logout, verify email, reset password
│   │   ├── onboarding.py          # 5-step onboarding wizard
│   │   ├── dashboard.py           # Main operational dashboard
│   │   ├── inventory.py           # Inventory list, detail, configure
│   │   ├── campaigns.py           # Campaign list and detail
│   │   ├── facility.py            # Equipment list, detail, work orders
│   │   ├── analytics.py           # Analytics dashboard and PDF export
│   │   ├── agent.py               # Agent logs and configuration settings
│   │   ├── shopper.py             # Shopper search portal
│   │   ├── notifications.py       # Notification centre
│   │   ├── settings.py            # Profile, team, billing, integrations hub
│   │   ├── superadmin.py          # Platform-level admin console
│   │   ├── api.py                 # Internal JSON API (agent status, KPIs, actions, payments)
│   │   ├── pwa.py                 # PWA manifest and offline page routes
│   │   └── push.py                # Push subscription registration and unsubscription
│   │
│   ├── services/                  # Business logic layer
│   │   ├── agent_runner.py        # Core agent missions: inventory SRS, campaign COS, facility FPS
│   │   ├── analytics_service.py   # KPI aggregation, trend computation, PDF report builder
│   │   ├── campaign_service.py    # COS computation, Gemini weather lookup, campaign copy generation
│   │   ├── inventory_service.py   # SRS computation, top at-risk SKU queries, chart data
│   │   ├── facility_service.py    # FPS computation, Z-score anomaly detection, telemetry charts
│   │   ├── shopper_service.py     # Gemini intent extraction, SKU ranking, navigation generation
│   │   ├── email_service.py       # All transactional email templates (verification, alerts, billing)
│   │   ├── push_service.py        # VAPID web push delivery via pywebpush
│   │   ├── razorpay_service.py    # Order creation, signature verification, payment fetch
│   │   ├── scheduler_service.py   # APScheduler setup, foot traffic simulator, sensor simulator
│   │   ├── notification_service.py# In-app notification creation and read state management
│   │   └── auth_service.py        # Token generation helpers
│   │
│   ├── forms/                     # WTForms form classes
│   │   ├── auth.py                # LoginForm, RegisterForm, ForgotPasswordForm, ResetPasswordForm
│   │   ├── onboarding.py          # Step1Form through Step5Form
│   │   ├── campaigns.py           # CampaignFilterForm
│   │   ├── facility.py            # WorkOrderForm, EquipmentForm
│   │   ├── inventory.py           # InventoryFilterForm
│   │   ├── settings.py            # ProfileForm, InviteTeamForm
│   │   └── shopper.py             # ShopperSearchForm
│   │
│   ├── templates/                 # Jinja2 HTML templates
│   │   ├── base.html              # Master layout with nav, CSP nonce, PWA meta tags
│   │   ├── auth/                  # Login, register, forgot password, reset, verify email
│   │   ├── onboarding/            # base_onboarding.html + step1.html through step5.html
│   │   ├── dashboard/             # Main dashboard with KPI tiles and chart widgets
│   │   ├── inventory/             # Inventory list, detail, configure pages
│   │   ├── campaigns/             # Campaign list and detail pages
│   │   ├── facility/              # Equipment list and detail pages
│   │   ├── analytics/             # Analytics dashboard with Chart.js visualisations
│   │   ├── agent/                 # Agent logs and settings pages
│   │   ├── shopper/               # Shopper search and results pages
│   │   ├── notifications/         # Notification centre
│   │   ├── settings/              # Hub, profile, team, billing, integrations
│   │   ├── superadmin/            # Platform admin console (8 pages)
│   │   ├── public/                # Landing, features, pricing, about, demo pages
│   │   ├── errors/                # 403, 404, 500 error pages
│   │   ├── partials/              # Reusable partials: nav, footer, alerts, pagination, KPI tile
│   │   └── offline.html           # PWA offline fallback page
│   │
│   └── utils/
│       └── decorators.py          # @role_required, @property_required decorators
│
├── static/                        # All static assets served by Flask
│   ├── manifest.json              # PWA Web App Manifest
│   ├── sw.js                      # Service Worker (pre-cache, offline fallback, background sync)
│   ├── browserconfig.xml          # Windows tile configuration
│   ├── css/                       # Per-page stylesheets
│   │   ├── main.css               # Global design tokens and shared components
│   │   ├── dashboard.css
│   │   ├── analytics.css
│   │   ├── auth.css
│   │   ├── campaigns.css
│   │   ├── facility.css
│   │   ├── inventory.css
│   │   ├── shopper.css
│   │   └── superadmin.css
│   ├── js/                        # Per-page JavaScript modules
│   │   ├── main.js                # Global utilities, notification polling
│   │   ├── dashboard.js           # Real-time KPI updates, foot traffic charts
│   │   ├── inventory.js           # SRS filtering, SKU detail charts
│   │   ├── campaigns.js           # Campaign activation / pause interactions
│   │   ├── facility.js            # Equipment telemetry charts, work order modals
│   │   ├── analytics.js           # Analytics charts, date range picker
│   │   ├── agent.js               # Agent log streaming, action approve/reject
│   │   ├── shopper.js             # Shopper search UI and result rendering
│   │   ├── settings.js            # Team management, billing checkout flow
│   │   ├── superadmin.js          # Platform admin table interactions
│   │   ├── pwa.js                 # PWA install prompt, SW registration, push subscribe
│   │   └── idb-service.js         # IndexedDB wrapper for offline sync queue
│   └── img/
│       └── offline-placeholder.svg
│
└── tests/                         # Test suite
    ├── test_models.py             # Unit tests for User, Inventory, Agent models
    ├── test_routes.py             # Integration tests for public, auth, dashboard, facility routes
    ├── test_services.py           # Service-layer tests for SRS, FPS, and notification logic
    └── test_pwa.py                # PWA-specific route and push subscription tests
```

---

## Getting Started

### Prerequisites

Before you start, make sure you have the following installed:

| Tool | Version | Install |
|---|---|---|
| Python | 3.9 or higher | [python.org](https://www.python.org/downloads/) |
| pip | Latest | Bundled with Python |
| Git | Any recent version | [git-scm.com](https://git-scm.com/) |
| A virtual environment tool | `venv` (built-in) | Built into Python 3 |

Optional but strongly recommended for production:

| Tool | Purpose |
|---|---|
| PostgreSQL | Production database |
| Gunicorn | Production WSGI server |
| Elasticsearch | Accelerated SKU and shopper search |

### Installation

**Step 1 — Clone the repository**

```bash
git clone https://github.com/shahram8708/RetailMind
cd RetailMind
```

**Step 2 — Create and activate a virtual environment**

On macOS and Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

On Windows (CMD):

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**Step 3 — Install Python dependencies**

```bash
pip install -r requirements.txt
```

**Step 4 — Configure environment variables**

```bash
cp .env.example .env
```

Open `.env` in your editor and fill in the values. At a minimum you need `SECRET_KEY` and `GEMINI_API_KEY` for the AI features to work. See the [Environment Variables](#environment-variables) section for a full breakdown.

**Step 5 — Initialize the database**

RetailMind defaults to SQLite for zero-config local development. The first run automatically creates all tables and seeds demo data:

```bash
python run.py
```

If you prefer to run migrations explicitly:

```bash
flask db upgrade
```

### Environment Variables

All configuration is driven by environment variables loaded from your `.env` file. Copy `.env.example` and fill in your values.

| Variable | Description | Example |
|---|---|---|
| `FLASK_ENV` | Runtime environment (`development` or `production`) | `development` |
| `SECRET_KEY` | 64-character random string for session signing | `your-random-64-char-secret-key` |
| `DATABASE_URL` | SQLAlchemy database URI | `sqlite:///retailmind.db` |
| `GEMINI_API_KEY` | Google Gemini API key from Google AI Studio | `AIzaSy...` |
| `RAZORPAY_KEY_ID` | Razorpay public key for payment processing | `rzp_live_...` |
| `RAZORPAY_KEY_SECRET` | Razorpay secret key for payment processing | `your-secret` |
| `RAZORPAY_WEBHOOK_SECRET` | Razorpay webhook signature verification secret | `your-webhook-secret` |
| `MAIL_SERVER` | SMTP server hostname | `smtp.gmail.com` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_USE_TLS` | Enable TLS for SMTP | `True` |
| `MAIL_USERNAME` | SMTP login username | `you@gmail.com` |
| `MAIL_PASSWORD` | SMTP app password | `your-app-password` |
| `MAIL_DEFAULT_SENDER` | From address for all outgoing email | `noreply@retailmind.ai` |
| `ES_CLOUD_ID` | Elasticsearch Cloud ID (optional) | `your-cloud-id` |
| `ES_API_KEY` | Elasticsearch API key (optional) | `your-es-api-key` |
| `BASE_URL` | Public base URL of the app | `https://retailmind.yourdomain.com` |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (optional, for future integrations) | `your-gcp-project` |
| `PWA_CACHE_VERSION` | Service Worker cache version string | `1.0.0` |
| `BACKGROUND_SYNC_ENABLED` | Enable PWA background sync queue | `True` |
| `VAPID_PUBLIC_KEY` | VAPID public key for Web Push | `BH...` |
| `VAPID_PRIVATE_KEY` | VAPID private key for Web Push | `your-private-key` |
| `VAPID_SUBJECT` | Contact URI included in push claims | `mailto:admin@retailmind.ai` |

> **Note on optional services:** RetailMind degrades gracefully when optional services are not configured. Missing Gemini credentials disable AI reasoning but the agent still creates fallback-text alerts. Missing Elasticsearch credentials fall back to SQL queries. Missing Razorpay credentials disable payment collection. Missing VAPID keys disable browser push notifications.

### Running the Project

**Development mode**

```bash
python run.py
```

The app starts at `http://localhost:5000`. Hot-reload is disabled by default (`use_reloader=False`) to prevent APScheduler from spawning duplicate background jobs.

Alternatively, use the Flask CLI:

```bash
flask --app run run --debug --host=0.0.0.0 --port=5000
```

**Production mode**

```bash
FLASK_ENV=production gunicorn wsgi:app --workers 3 --bind 0.0.0.0:8000
```

For a high-traffic deployment, add a `--timeout` and run behind a reverse proxy like Nginx:

```bash
gunicorn wsgi:app --workers 4 --worker-class sync --timeout 120 --bind 127.0.0.1:8000
```

---

## Usage

**Superadmin login (seeded automatically)**

When the database is empty, `app/seed.py` runs automatically and creates a superadmin account, a demo property, demo tenants, inventory items, campaigns, equipment, sensor readings, and agent actions. Check the seed file for default credentials if you want to log in immediately:

```bash
grep -n "superadmin\|password\|email" app/seed.py | head -20
```

**Typical workflow for a new mall admin**

1. Register at `/auth/register` (or be invited by superadmin).
2. Complete the 5-step onboarding at `/onboarding/step/1`: set property details, configure tenants and floors, link inventory data sources, invite team members, and configure agent thresholds.
3. Land on the main dashboard at `/dashboard` — real-time KPI tiles, foot traffic chart by zone, and the agent action queue.
4. Approve or reject agent-raised inventory restock actions from the action panel.
5. View per-SKU risk detail at `/inventory/{sku_id}` with SRS trend charts and stockout history.
6. Navigate to `/campaigns` to see AI-generated campaign opportunities and activate them.
7. Check `/facility` for equipment health scores and open work orders.
8. Run the full analytics report from `/analytics` and export it as a PDF.
9. Adjust agent thresholds and mission schedules at `/agent/settings`.

**Shopper portal**

Shoppers access the platform at `/shopper`. They type a natural-language query like "black running shoes under 5000 rupees size 10" and receive ranked results from across all tenants in the mall, complete with store location, floor, and zone navigation.

**Running an agent mission manually**

Admin users can trigger any mission on demand via the dashboard without waiting for the scheduler:

```
POST /api/agent/run-now/inventory
POST /api/agent/run-now/campaign
POST /api/agent/run-now/facility
```

---

## API Documentation

All API endpoints live under the `/api` prefix and return JSON. Most require an active session (cookie-based login). CSRF protection is enforced on mutation endpoints using Flask-WTF.

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `GET` | `/api/agent/status` | Yes | Returns current agent configuration, last-run timestamps, and recent action counts for all four missions |
| `GET` | `/api/notifications/unread` | Yes | Returns the count of unread in-app notifications for the current user |
| `POST` | `/api/actions/<action_id>/approve` | Yes | Approves a pending agent action (restock, campaign launch, work order) |
| `POST` | `/api/actions/<action_id>/reject` | Yes | Rejects a pending agent action with an optional reason |
| `GET` | `/api/kpi/summary` | Yes | Returns the four headline KPIs: active missions, inventory alerts today, active campaigns this week, open work orders |
| `GET` | `/api/health-check` | No | Health check endpoint; returns `{"status": "ok"}` with uptime and version |
| `GET` | `/api/pwa/config` | No | Returns VAPID public key and PWA feature flags for client-side PWA initialisation |
| `POST` | `/api/sync/queue` | Yes | Accepts batched offline mutation events from the IndexedDB sync queue and replays them |
| `GET` | `/api/foot-traffic/current` | Yes | Returns current foot traffic counts per zone (A through E) |
| `GET` | `/api/inventory/risk` | Yes | Returns the top at-risk SKUs with SRS scores for the current property |
| `GET` | `/api/campaigns/opportunities` | Yes | Returns campaigns with status `opportunity` and their COS scores |
| `POST` | `/api/campaigns/<campaign_id>/activate` | Yes | Activates a campaign opportunity |
| `POST` | `/api/campaigns/<campaign_id>/pause` | Yes | Pauses an active campaign |
| `GET` | `/api/facility/anomalies` | Yes | Returns equipment with active sensor anomalies |
| `GET` | `/api/analytics/data` | Yes | Returns chart datasets (foot traffic, sales velocity, campaign performance) for a given date range |
| `POST` | `/api/agent/run-now/<mission_type>` | Yes | Triggers an immediate agent mission run (`inventory`, `campaign`, `facility`, `shopper`) |
| `GET` | `/api/admin/platform-stats` | Superadmin | Returns platform-wide stats: total properties, users, revenue, and active subscriptions |
| `POST` | `/api/shopper/search` | No | Accepts a shopper query and returns intent-parsed, ranked SKU results |
| `POST` | `/api/payment/create-order` | Yes | Creates a Razorpay order for the given plan and billing cycle |
| `POST` | `/api/payment/verify` | Yes | Verifies Razorpay payment signature and activates the subscription |

**Example: Approve an agent action**

```bash
curl -X POST https://your-domain.com/api/actions/42/approve \
  -H "Content-Type: application/json" \
  -b "session=<your-session-cookie>"
```

Response:

```json
{
  "status": "ok",
  "action_id": 42,
  "new_status": "approved"
}
```

**Example: Shopper search**

```bash
curl -X POST https://your-domain.com/api/shopper/search \
  -H "Content-Type: application/json" \
  -d '{"query": "blue denim jacket under 3000", "property_id": 1}'
```

Response:

```json
{
  "results": [
    {
      "sku_id": "TNT-SKU-004",
      "product_name": "Slim Fit Denim Jacket",
      "brand": "Levi's",
      "unit_price": 2799,
      "store": "Levi's Store",
      "zone": "B",
      "floor": 2
    }
  ],
  "intent": {
    "category": "jackets",
    "color": "blue",
    "max_price": 3000
  }
}
```

---

## Configuration

**`app/config.py`**

Three configuration classes control runtime behaviour:

| Class | `FLASK_ENV` value | Behaviour |
|---|---|---|
| `DevelopmentConfig` | `development` | Debug mode on, insecure cookies, PWA dev mode (no caching) |
| `ProductionConfig` | `production` | Debug off, secure cookies, HTTPS redirect enforced, 1-year static asset caching |
| `TestingConfig` | `testing` | CSRF disabled, in-memory SQLite, no scheduler |

Key defaults to know:

| Setting | Default | Notes |
|---|---|---|
| `CACHE_DEFAULT_TIMEOUT` | 300 seconds | SimpleCache TTL |
| `RATELIMIT_DEFAULT` | `200 per day; 50 per hour` | Applied globally via Flask-Limiter |
| `PERMANENT_SESSION_LIFETIME` | 8 hours | Session expiry for logged-in users |
| `REMEMBER_COOKIE_DURATION` | 30 days | "Remember me" cookie lifetime |
| `WTF_CSRF_TIME_LIMIT` | 3600 seconds | CSRF token validity window |

**Agent thresholds (per-property, stored in `agent_configurations`)**

| Threshold | Default | Description |
|---|---|---|
| `inventory_srs_threshold` | 0.70 | SRS score above which an inventory alert is raised |
| `campaign_cos_threshold` | 0.75 | COS score above which a campaign opportunity is surfaced |
| `facility_fps_threshold` | 0.65 | FPS score above which a maintenance action is raised |
| `inventory_check_interval_minutes` | 15 | How often the inventory mission runs |
| `campaign_check_interval_minutes` | 30 | How often the campaign mission runs |
| `facility_check_interval_minutes` | 10 | How often the facility mission runs |

These are all adjustable per property from the Agent Settings page at `/agent/settings`.

**Subscription plans (defined in `razorpay_service.py`)**

| Plan | Monthly (INR) | Annual (INR) |
|---|---|---|
| Starter | 49,999 | 39,999 |
| Professional | 1,49,999 | 1,19,999 |
| Enterprise | Contact Sales | Contact Sales |

---

## Testing

RetailMind has a full test suite using Python's built-in `unittest` framework, runnable via `pytest`.

**Run the complete test suite:**

```bash
pytest -q
```

**Run a single test file:**

```bash
pytest tests/test_models.py -q
pytest tests/test_routes.py -q
pytest tests/test_services.py -q
pytest tests/test_pwa.py -q
```

**Run with verbose output:**

```bash
pytest -v
```

All tests use an in-memory SQLite database configured through `TestingConfig`. CSRF protection is disabled in test mode. The test suite covers:

`test_models.py` — User password hashing and verification, role routing logic, property and tenant model relationships, agent action creation and status transitions.

`test_routes.py` — All public page routes (landing, features, pricing, about, demo), the login page, authenticated dashboard access, facility work order creation, and redirect behaviour for unauthenticated users.

`test_services.py` — SRS score computation for at-risk and healthy SKUs, FPS score computation for equipment with sensor anomalies, in-app notification creation, mark-as-read, and unread count queries.

`test_pwa.py` — PWA manifest and offline page routes, push notification subscription registration and retrieval for authenticated users.

---

## Deployment

**Production with Gunicorn**

Make sure `FLASK_ENV=production` is set in your `.env`. Then:

```bash
pip install gunicorn
gunicorn wsgi:app --workers 4 --bind 0.0.0.0:8000 --timeout 120
```

**With Nginx as a reverse proxy (recommended)**

A minimal Nginx config to sit in front of Gunicorn:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location /static/ {
        alias /path/to/RetailMind/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

**PostgreSQL for production**

```bash
pip install psycopg2-binary
```

Set in `.env`:

```
DATABASE_URL=postgresql://user:password@localhost:5432/retailmind
```

Then run:

```bash
flask db upgrade
```

**Generating VAPID keys for Web Push**

```bash
pip install py-vapid
python -c "from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print('Public:', v.public_key); print('Private:', v.private_key)"
```

Paste the output into `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` in your `.env`.

**Environment variables in production**

Never commit your `.env` to version control. In production, export variables directly from your server environment or use a secrets manager:

```bash
export SECRET_KEY="your-64-char-production-secret"
export FLASK_ENV="production"
export DATABASE_URL="postgresql://..."
```

There is no Docker or CI/CD configuration included in this repository at present. See [Roadmap](#roadmap) for planned additions.

---

## Contributing

Contributions are welcome. Here is how to get involved:

**Step 1 — Fork the repository**

Click the Fork button on GitHub and clone your fork locally:

```bash
git clone https://github.com/YOUR_USERNAME/RetailMind
cd RetailMind
```

**Step 2 — Create a feature branch**

```bash
git checkout -b feature/your-feature-name
```

**Step 3 — Make your changes**

Follow these conventions:

All Python code should be readable and follow PEP 8. Business logic goes in `app/services/`. Route handlers in `app/routes/` should stay thin — validate the request, call a service, return the response. Models in `app/models/` should not contain business logic.

For frontend changes, keep JavaScript modular and page-scoped. Avoid adding new CDN dependencies without discussion.

**Step 4 — Run the tests**

```bash
pytest -q
```

Make sure all existing tests pass before opening a PR.

**Step 5 — Commit and push**

```bash
git add .
git commit -m "feat: describe what your change does"
git push origin feature/your-feature-name
```

**Step 6 — Open a Pull Request**

Go to the original repository on GitHub and open a PR from your branch. Describe what you changed and why.

**Reporting bugs**

Open a GitHub Issue and include:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your Python version and OS
- Any relevant error messages or stack traces

**Requesting features**

Open a GitHub Issue with the `feature request` label. Describe the use case — not just the solution.

---

## Roadmap

Based on the current codebase and visible gaps, here is what is done and what is natural next:

**Done**

- AI agent with four autonomous missions (inventory, campaign, facility, shopper)
- SRS, COS, and FPS scoring algorithms with Gemini 2.5 Flash reasoning
- 5-step onboarding wizard
- Role-based access control across 6 roles
- Progressive Web App with full offline support and background sync
- Web Push notifications via VAPID
- Razorpay payment integration with subscription management
- PDF analytics export via ReportLab
- Elasticsearch integration with graceful SQL fallback
- Superadmin platform console
- Test suite covering models, routes, services, and PWA

**Planned / In Progress**

- Docker and `docker-compose.yml` for one-command local setup
- CI/CD pipeline configuration (GitHub Actions)
- Multi-property orchestration for Enterprise tenants
- Webhook endpoint for Razorpay payment events
- Real POS system and inventory management integrations (currently simulator-driven)
- Data export as CSV in addition to PDF
- Two-factor authentication
- In-app chat or comment threads on agent actions
- Dedicated mobile app (currently PWA covers this use case)

---

## License

No `LICENSE` file was found in this repository. The project does not currently specify a license.

If you are the author and want to open-source this work, consider adding an [MIT License](https://choosealicense.com/licenses/mit/) or [Apache 2.0](https://choosealicense.com/licenses/apache-2.0/). Without a license, the default copyright applies and no one has permission to use, modify, or distribute the code.

---

## Acknowledgements

RetailMind is built on the shoulders of several excellent open-source projects and commercial APIs:

- [Flask](https://flask.palletsprojects.com/) — the web framework at the core of everything
- [SQLAlchemy](https://www.sqlalchemy.org/) and [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) — ORM that makes the data model clean
- [Bootstrap 5](https://getbootstrap.com/) — UI components and responsive grid
- [Chart.js](https://www.chartjs.org/) — all the charts on dashboards and analytics pages
- [Google Gemini](https://ai.google.dev/) — Gemini 2.5 Flash powers the AI reasoning, weather lookup, campaign copy generation, and shopper intent extraction
- [Razorpay](https://razorpay.com/) — payment gateway for INR subscriptions
- [APScheduler](https://apscheduler.readthedocs.io/) — the background scheduler that runs all four agent missions on configurable intervals
- [ReportLab](https://www.reportlab.com/) — PDF report generation for the analytics export
- [pywebpush](https://github.com/web-push-libs/pywebpush) — VAPID-based Web Push delivery
- [Elasticsearch](https://www.elastic.co/) — optional search acceleration for shopper queries and inventory lookups

---

## Contact / Author

**Author:** Shahram  
**GitHub:** [github.com/shahram8708](https://github.com/shahram8708)  
**Repository:** [github.com/shahram8708/RetailMind](https://github.com/shahram8708/RetailMind)

If you have questions, found a bug, or just want to talk about AI-powered retail operations — open an issue on GitHub. The project is actively maintained and contributions are genuinely welcome.