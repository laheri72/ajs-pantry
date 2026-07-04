# AJS Pantry — Deep Repository Analysis & Project Memory

---

## 1. What The Project Does:

AJS Pantry is a **production-hardened, multi-tenant SaaS platform** for managing residential hostel pantry operations. It serves multiple "tenants" (hostel organizations), each with multiple floors and a full hierarchy of roles. Core functionality covers:

- **Meal scheduling** — smart rotation, bulk planning, dish library with performance insights
- **Procurement** — shopping lists, assignments, bulk completion, receipt OCR scanning
- **Finance** — bills, budget cycles, expense ledger, PDF print reports, Faculty oversight
- **Faculty workflow** — a tenant-wide office role that allocates per-floor budgets, collects report PDFs, verifies them, manages active non-admin users, imports members from Excel, and reviews meal reception
- **Tea duty scheduling** — rotation assignment, conflict-aware auto-assignment
- **Community tools** — announcements, special events, suggestions with voting, meal evaluations
- **Inter-floor lending** — item tracking with lender/borrower verification flow
- **PWA** — installable, offline-capable, push notification support

---

## 2. Tech Stack & Architecture

### Stack
| Layer | Technology |
|---|---|
| Backend | Flask 3.1.x, Python 3.11+ |
| ORM | Flask-SQLAlchemy + SQLAlchemy 2.0 |
| Migrations | Flask-Migrate (Alembic) |
| Database | PostgreSQL via Supabase (`psycopg2-binary`) |
| Frontend | Jinja2, Bootstrap 5, Vanilla JS/CSS |
| Background Jobs | RQ (Redis Queue) with sync fallback |
| Caching | Flask-Caching (Redis → SimpleCache fallback) |
| OCR | Tesseract + pdfplumber |
| Push | pywebpush (VAPID) |
| Email | Gmail SMTP (async via RQ) |
| PWA | Service Worker, Web App Manifest |
| Hosting | Oracle Always-Free ARM VM, Nginx, Gunicorn |
| CI/CD | GitHub Actions → SSH deploy |

### Architecture Pattern
```
User → Firebase/DNS → Nginx (TLS) → Gunicorn → Flask App
                                                   ↓
                              Blueprint Router (auth/pantry/finance/ops/admin/faculty/super_admin)
                                                   ↓
                              SQLAlchemy ORM (global tenant isolation via do_orm_execute listener)
                                                   ↓
                              Supabase PostgreSQL
```

### Multi-Tenancy Model
Tenant isolation is enforced **at the ORM layer** through a `do_orm_execute` listener in `models.py`. Every SELECT query on models inheriting `TenantMixin` automatically receives a `WHERE tenant_id = g.tenant_id` filter. This is the single most important security mechanism — it's invisible to developers and prevents cross-tenant data leaks even if a filter is accidentally omitted.

### Role Hierarchy
```
super_admin  → Platform-wide (no tenant)
faculty      → Tenant-wide office: budget cycles, reports, member management, imports, meal insights
admin        → All floors in a tenant
pantryHead   → Single floor management
teaManager   → Tea scheduling only
member       → Personal feed & feedback
```

---

## 3. Current Strengths

**Architecture:**
- ORM-level tenant isolation is industry-grade and nearly impossible to bypass accidentally
- Blueprint modularization is clean and domain-driven
- Global event listener pattern for tenancy is elegant and scalable

**Performance (completed as of April 2026):**
- Redis caching on `/dashboard` aggregate queries (5-minute TTL with smart invalidation)
- Composite indexes on `(tenant_id, floor)` on all heavy tables
- Calendar uses bounded date ranges to limit payload
- RQ workers for OCR, push notifications, and email

**Operational:**
- Fully automated CI/CD with auto-migrations on push to `main`
- No single-point-of-failure on configuration (fails loud at boot if secrets are missing)
- Graceful Redis fallback to SimpleCache and sync task execution

**Feature completeness:**
- Faculty workflow is a full office system (budget allocate → submit → verify → close, plus member import/role management and meal insights)
- Receipt OCR supports D-Mart, Blinkit, and a robust generic parser
- Smart menu rotation with absence conflict detection
- Bulk tea assignment with preview and confirmation flow
- Ad-hoc PDF storage for irregular expense reports
- Faculty mobile portal with off-canvas navigation

---

## 4. Weaknesses & Key Risks

### Critical
| Issue | Risk | Location |
|---|---|---|
| No CSRF protection | All POST forms are vulnerable to CSRF attacks | App-wide |
| Absolute paths in `FacultyReportSubmission.storage_path` | Local dev uploads can corrupt production DB paths | `blueprints/faculty/routes.py` |
| Direct `flask db upgrade` on production in CI/CD | Failed migration leaves schema in corrupted half-state | `.github/workflows/deploy.yml` |

### High
| Issue | Risk | Location |
|---|---|---|
| No staging environment | Every deploy goes directly to production | Infrastructure |
| Partial rate limiting | V1 protects auth and OCR bill upload; remaining write/API endpoints still need throttling later | `app.py`, `blueprints/rate_limit_keys.py` |
| `PushSubscription` not normalized | Table will bloat with stale device tokens | `models.py` |
| Partial soft deletes only | `User.is_active` supports Faculty deactivation, but bills and other records still need soft-delete strategy | Multiple blueprints |

### Medium
| Issue | Risk | Location |
|---|---|---|
| Dependency drift risk | Keep `requirements.txt`, `pyproject.toml`, and `uv.lock` in sync after package changes | Dependency files |
| Dual logout timer (server 15min + JS inactivity) | Inconsistent UX on shared PCs | `app.py`, `static/script.js` |
| `tea` rotation not automated | Manual assignment burden grows with scale | `blueprints/ops/routes.py` |
| Tenant audit coverage is partial | `TenantAuditLog` records Faculty member mutations/imports; extend it to budget, bill, and finance mutations | `models.py`, `blueprints/utils.py` |

---

## 5. Project Memory — Structured Reference

This section captures all decisions, patterns, and context needed to continue development as a co-developer without re-reading the codebase.

---

### 5A. Core Conventions

**Blueprint naming:**
- The admin blueprint is registered as `admin_panel` (not `admin`) — always use `url_for('admin_panel.admin')`, never `url_for('admin.admin')`
- Faculty blueprint is `faculty` — shared non-faculty routes inside it (`/reports`, `/reports/<id>/download`) are exempted from faculty auth guard via `shared_staff_endpoints` set

**Tenant context:**
- Always use `getattr(g, 'tenant_id', None)` when setting `tenant_id` on new model instances
- Never use `tenant_filter()` directly inside model methods — only in route/service layer
- Super admin bypasses tenant filter via `g.is_super_admin = True`

**Floor handling:**
- `FLOOR_MIN = 1`, `FLOOR_MAX = 11` (overridden per tenant by `tenant.floor_count`)
- Admin can switch active floor via `session['active_floor']`
- All other roles use their own `user.floor` directly
- `_get_active_floor(user)` handles this logic centrally

**Schema changes workflow:**
1. Edit `models.py`
2. `flask db migrate -m "description"` locally
3. Commit the new migration file
4. Push to `main` — CI/CD auto-upgrades Supabase

---

### 5B. Faculty Workflow Deep Reference

The Faculty system is the most complex feature. Key architectural decisions:

**Budget flow:**
```
FacultyBudgetCycle (tenant-wide) 
  → Budget rows (one per floor, cycle_id set)
  → Expenses/Bills tracked against cycle date range
  → FacultyReportSubmission (one per floor per cycle)
    → linked to ExpensePrintReport (saves bill selection)
    → linked to Bills (via bill.report_submission_id)
    → PDF stored on Oracle filesystem
```

**Visibility rule for budgets** (`visible_budget_condition()`):
- Manual budgets: always visible (`cycle_id IS NULL`)
- Faculty cycle budgets: visible only when cycle status is NOT 'draft'

**Active cycle constraint:** Only one `FacultyBudgetCycle` can have `status='active'` at a time per tenant.

**Critical auth exception:** `/reports` and `/reports/<id>/download` live inside the faculty blueprint but must be accessible to `admin` and `pantryHead`. They are in `shared_staff_endpoints` set in both `app.py` (`enforce_tenancy`) and `blueprints/faculty/routes.py` (`_faculty_auth_guard`).

**Storage path risk:** `FacultyReportSubmission.storage_path` currently stores absolute paths. If uploaded from local dev pointing at production DB, you get Windows paths in the DB. **Rule: only upload Faculty PDFs through the deployed Oracle app.** Future fix: store relative paths only.

**Cycle delete cascade** (`_delete_cycle_related_data`): deletes Budget rows, FacultyReportSubmission rows (+ disk PDFs), ExpensePrintReport rows (+ bill links), then the cycle itself.

**Faculty member management (May 2026):**
- `/faculty/members` lists only active Faculty-visible users: `role NOT IN ('admin', 'super_admin')` and `is_active = true`
- The canonical helper is `faculty_visible_users_query()` in `blueprints/utils.py`
- Faculty can assign/demote only `member`, `pantryHead`, and `teaManager`
- Faculty soft-deactivates users by setting `User.is_active = false`; historical records are preserved
- Faculty cannot manage `admin`, `super_admin`, or other `faculty` accounts from this page

**Excel onboarding (May 2026):**
- Template route: `/faculty/import/template`
- Validation route: `/faculty/import/validate`
- Commit route: `/faculty/import/commit`
- Excel headers must be exactly `TR`, `Name`, `Floor`
- Backend uses `openpyxl`; frontend uses SheetJS only as optional pre-validation
- TR and generated email remain globally unique; duplicate TR/email anywhere in the platform is rejected
- New imported members use `email = f"{TR}@jameasaifiyah.edu"`, default password `maskan1447`, `is_first_login = true`, `is_active = true`
- Partial import is supported: valid rows are inserted, invalid rows are reported

**Faculty meal insights (May 2026):**
- `/faculty/meal-insights` uses existing models only
- Upcoming and historical meals come from `Menu`
- Reception is aggregated from `Feedback.menu_id`
- Request/vote signal is aggregated through `Suggestion.dish_id` and `SuggestionVote`
- There is no served-meal model yet; label these metrics as planned/scheduled meals or reception, not served meals

**Faculty caching (May 2026):**
- `_get_faculty_dashboard_stats(tenant_id)` is memoized for 300 seconds
- Invalidate it after Faculty import, role change, and deactivation via `_clear_faculty_dashboard_cache()`

---

### 5C. Budget Ledger Logic

`build_floor_budget_ledger()` in `blueprints/budgeting.py` is the central finance calculation engine. It:
1. Fetches all Budget rows for the floor (filtered by `visible_budget_condition`)
2. Builds "periods" with opening balance, allocation, spent, closing balance
3. Identifies the "current period" — either the active cycle's allocation or the latest manual budget
4. Calculates `carryforward_balance` for display purposes
5. Returns a comprehensive dict used by Expenses, Dashboard, and Reports pages

**Key returned fields:**
- `current_allocated_amount` — new money in this period
- `current_available_budget` — opening balance + new allocation (what you can spend)
- `current_spent_amount` — bills + legacy expenses in this period
- `current_remaining_balance` — available minus spent
- `carryforward_balance` — the closing balance that carries into next period

---

### 5D. Dashboard Caching Pattern

```python
@cache.memoize(timeout=300)
def _get_dashboard_stats(tenant_id, floor):
    # Heavy aggregates here

def _clear_dashboard_cache(tenant_id, floor):
    cache.delete_memoized(_get_dashboard_stats, tenant_id, floor)
```

`_clear_dashboard_cache()` must be called in every route that modifies financial or operational data. It's currently called in: bill creation/deletion, expense deletion, budget add/delete, tea task changes, procurement changes, request status changes, special event creation.

---

### 5E. Background Job Architecture

RQ is configured in `app.py` with graceful fallback:
```python
try:
    redis_conn = Redis.from_url(redis_url)
    redis_conn.ping()  # Test connection
    app.task_queue = Queue("ajs_pantry_tasks", connection=redis_conn)
    # Redis cache active
except Exception:
    app.task_queue = None  # Sync fallback
    # SimpleCache active
```

**Async-capable functions:**
- `send_push_notification()` → `_send_push_worker()`
- `send_email_notification()` → `_send_email_worker()`
- Receipt import → `_process_receipt_worker()`

All three check `hasattr(current_app, 'task_queue') and current_app.task_queue` before enqueueing. If Redis is down, they execute synchronously inline.

---

### 5F. OCR Receipt Pipeline

**Flow:** Upload → `ParserFactory.get_text()` (PDF: pdfplumber, Image: Tesseract) → `ParserFactory.get_parser()` (detect store) → `parser.parse(text)` → `ReceiptData`

**Store detection:** D-Mart (`AVENUE E-COMMERCE`, `DMART`), Blinkit (`BLINKIT`, `GROFERS`, `BIGWAY MARKETING`), else `GenericParser`

**Async path:** If RQ available, file saved to `tmp/receipts/`, job enqueued, client polls `/expenses/import-status/<task_id>`

**Sync path:** Direct processing, immediate JSON response

**Full reconcile endpoint** (`/reconcile/atomic/full`): Creates bill + new ProcurementItems + reconciles existing ProcurementItems in a single atomic transaction.

---

### 5G. Feedbacks & Suggestions Merge

The UI merged `Suggestions` and `Feedbacks` into one page (`/feedbacks`), but the **data models are separate**:
- `Feedback` — meal ratings, drives leaderboards and analytics
- `Suggestion` — ideas with votes, linked to `Dish` for contextual display
- `/suggestions` GET redirects to `/feedbacks#suggestions`
- Both POST actions handled in `feedbacks()` via `form_type` hidden field

---

### 5H. Notification System

**Push notifications** flow through `PushSubscription` table. Stale tokens (404/410 responses from push service) are automatically deleted. VAPID keys must be in `.env` as `VAPID_PRIVATE_KEY` and `VAPID_PUBLIC_KEY`.

**Email notifications** use Gmail SMTP SSL on port 465. Credentials: `GMAIL_USER`, `GMAIL_PASS`.

**Internal email endpoint** (`/internal/send-email`): Protected by `X-SECRET` header matching `INTERNAL_API_SECRET`. Used by external services (Supabase Edge Functions) to trigger emails.

---

### 5I. Menu Intelligence Features

**Dish Library** (`Dish` model): Shared pool of dishes per tenant. Category: `main`, `side`, `both`.

**Smart Rotation** (`_get_next_team_in_rotation()`): Finds team that served least recently based on non-buffer menus. Integrates with absence checking.

**Dish Insights** (`/menus/dish-insights/<id>`): Returns avg rating, champion team, top 3 suggestions for a dish. Displayed inline when scheduling.

**Bulk Planner**: Generates 7-day schedule with rotation preview, conflict warnings, Tom Select searchable dropdowns per day.

**Buffer Day**: When `is_buffer=True`, individual assignment is used instead of team rotation. Doesn't advance the rotation index.

---

### 5J. Super Admin Platform

Entirely separate portal at `/platform-admin/`. Key operations:
- Provision new tenants (creates Tenant + admin user atomically)
- Toggle tenant active/suspended status
- Manage Faculty accounts (provision, reset password, update email/TR)
- Toggle `faculty_workflow_enabled` per tenant
- View cross-tenant analytics (financial util, completion rate, at-risk tenants)
- Platform audit log (`PlatformAudit` model)

---

### 5K. Deployment Configuration

- **Systemd web service:** `/etc/systemd/system/ajs-pantry.service`
- **Systemd worker service:** `/etc/systemd/system/rq-worker.service` runs `/home/ubuntu/ajs-pantry/venv/bin/rq worker ajs_pantry_tasks`; keep the repo template in `deploy/ajs-pantry-worker.service` in sync. The critical production fix is `Restart=always` because the old worker stayed dead after transient Redis/Upstash errors.
- **Environment:** `/home/ubuntu/ajs-pantry/.env`
- **Report storage:** `REPORT_STORAGE_ROOT` env var, defaults to `~/ajs-pantry-data/reports`
- **Production target:** `/home/ubuntu/ajs-pantry-data/reports/<tenant-slug>/`

**Required env vars:**
- `SESSION_SECRET` — Flask session key (required, app won't start without it)
- `INTERNAL_API_SECRET` — Internal email endpoint protection
- `DATABASE_URL` or `SUPABASE_DATABASE_URL` — PostgreSQL connection
- `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY` — Push notifications
- `GMAIL_USER`, `GMAIL_PASS` — Email
- `REDIS_URL` — Background jobs (optional, falls back gracefully)
- `RATE_LIMIT_STORAGE_URL` — Optional dedicated Redis/Upstash Redis URL for rate-limit counters; falls back to `REDIS_URL`, then in-memory local/dev storage
- `TRUST_PROXY_HEADERS` — Optional proxy header toggle for real client IPs behind Nginx/Oracle proxy; defaults to enabled, set `0` only if the app is directly internet-exposed
- `RECEIPT_IMPORT_ASYNC_ENABLED` — Receipt OCR queue toggle; defaults to off on Windows/dev and on for Linux production
- `RECEIPT_TEMP_FILE_TTL_SECONDS` — Cleanup age for `tmp/receipts` files, default `300`
- `REPORT_STORAGE_ROOT` — Faculty PDF storage path
- `SUPABASE_SERVICE_ROLE_KEY` — Bulk menu email edge function

---

### 5L. Rate Limiting V1 (May 2026)

Implemented with `Flask-Limiter[redis]` in `app.py`.

**Storage behavior:**
- Uses `RATE_LIMIT_STORAGE_URL` when set.
- Falls back to `REDIS_URL` so existing Upstash Redis can store counters.
- Falls back to in-memory storage for local/dev when Redis is not configured.
- `TRUST_PROXY_HEADERS` defaults to enabled so Oracle/Nginx `X-Forwarded-For` is respected via `ProxyFix`.

**Protected in V1:**
- Member login `/login`
- Staff login `/staff-login`
- Faculty login `/faculty/login`
- Super Admin login `/platform-admin/login`
- OCR bill import `/expenses/import-receipt`

**Deferred intentionally:**
- Internal email endpoint
- Faculty/member Excel imports
- Push subscription
- Notification dispatch endpoints
- General write/API endpoints

The shared limiter object lives in `app.py`; request key helpers live in `blueprints/rate_limit_keys.py`.

---

### 5M. Migration Chain (as of May 2026)

```
bdd4590fc68f  initial migration
  → b83ed1c2648f  add skip_notifications to Menu
  → e2a2b6f7d4c1  faculty budget cycles + report submissions
  → a7b91f5c2d44  expense print reports
  → f3c4e8a1b2d9  faculty messages
  → e8be6e260d2f  faculty_report_submission constraint + allocated_amount
  → 0cce95996e99  final model alignment (index naming)
  → 3f8cf96330f8  composite indexes (tenant_id, floor)
  → 8ee30d5a76d9  PDF storage columns on ExpensePrintReport
  → 9b7f2a6c4d11  tenant faculty_workflow_enabled toggle
  → a1b2c3d4e5f6  enable RLS on faculty tables (Supabase)
  → d4e5f6a7b8c9  global dish estimates + dish audit log
  → e5f6a7b8c9d0  seed dish estimates
  → fix_estimates_v2  fix estimates v2
  → c6d7e8f9a0b1  user soft delete + tenant audit log
```

### 5N. UI Multi-Theme & Interactive Calendar Engine (July 2026)
*   **Theme Selection System:** Introduces four light-mode themes and preserves the original dark mode for members and pantry heads. Selected themes are persisted in local storage (`selected-theme`) and synced backward to `theme` for device consistency.
    1.  *Teal Green (Default)*
    2.  *Navy Blue:* Ocean branding theme using a ship steering wheel SVG helm icon in the selector dropdown.
    3.  *Platinum Elegance:* Light, airy slate/silver expensive styling.
    4.  *Imperial Saffron & Gold:* Saffron orange color scheme accented with gold.
*   **FOUC Prevention:** Inside `base.html`, an inline self-contained JavaScript block runs immediately post-`<body>` parsing to load the theme from local storage and add the target theme classes to the document body prior to render/layout paint.
*   **Circular Badge Header Trigger:** To maintain high visibility across themes, the theme selector dropdown is triggered by a circular white/light-grey badge (`.app-theme-button`) in the navbar. Dropdown elements synchronize active selections with a checkmark symbol and theme-colored highlight states.
*   **Calendar Highlights & Interactions:**
    1.  *Current Day separation:* Today is styled with a distinct Indigo theme (solid circular date badge and background tint) to prevent visual clashes with the teal cooking rotation turns.
    2.  *Card elevation transition:* Calendar day cards scale and elevate on hover (`translateY(-3px)`), casting drop shadows and border outlines matching the active theme's colors.
    3.  *Input collision prevention:* Suggestion forms dynamically toggle text fields and dropdowns on selection change to prevent duplicate entries and database crashes.

---


## 6. Next Development Priorities

Based on the codebase state and architecture audit, here's the suggested roadmap:

**Immediate (security-critical):**
1. **CSRF Protection** — Add Flask-WTF or manual CSRF tokens to all state-changing POST forms
2. **Relative path storage** — Migrate `FacultyReportSubmission.storage_path` and `ExpensePrintReport.storage_path` to relative paths from `REPORT_STORAGE_ROOT`

**Short-term (operational stability):**
3. **Pre-deploy DB backup** — Add `pg_dump` step in `.github/workflows/deploy.yml` before migration
4. **Rate limiting follow-up** — V1 protects auth routes and OCR bill upload; later add limits for internal email, notification dispatch, Excel imports, push subscription, and other write/API endpoints
5. **Keep dependency files synchronized** — `requirements.txt`, `pyproject.toml`, and `uv.lock` are now aligned; keep them that way when adding packages

**Medium-term (features):**
6. **Tea Smart Rotation** — Mirror the Menu Smart Rotation system for tea duty
7. **Expand TenantAuditLog coverage** — Faculty member mutations/imports are logged; add budget modifications, bill deletions, and finance actions next
8. **PushSubscription normalization** — Add `device_id`, `last_active_at`, and periodic cleanup of dead tokens

I'm now fully onboarded as your AI co-developer. In each future conversation within this project, reference specific files or features by name and I'll have the full context to assist effectively — whether that's generating new routes, debugging a migration, writing a new blueprint, or designing a new feature from scratch.

---

## 7. Terminology mapping

The codebase uses "Team" internally (DB tables, model classes, Python variables, 
JS IDs). Users see "Room" everywhere in the UI. This is intentional and managed 
via `config/terms.py` + a Jinja2 context processor.

| Internal (code)     | User-facing (UI)  |
|---------------------|-------------------|
| Team                | Room              |
| TeamMember          | Member            |
| team (DB table)     | room (UI label)   |
| assignedTeamSelect  | "Assigned Room"   |
| icon (DB column)    | Room No. / Label  |

To change UI terminology: edit `config/terms.py` only.
Do NOT rename model classes, DB tables, or JS identifiers.
