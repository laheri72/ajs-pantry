# AJS Pantry — Future Scalability & Evolution Audit
**Date:** February 26, 2026
**Focus:** 6–12 Month Production Growth Trajectory

---

## PHASE 1 — FUTURE RISKS

### 1. Synchronous External Dependencies Locking WSGI Workers
Currently, Tesseract OCR (`ParserFactory.process_receipt`) and Push Notifications (`pywebpush.webpush`) execute synchronously within the request-response cycle. As user activity scales, simultaneous receipt uploads or floor-wide announcements will block Gunicorn workers for seconds at a time. On an Oracle Free Tier ARM VM, this will rapidly exhaust the worker pool, causing `502 Bad Gateway` and `504 Gateway Timeout` errors across the entire platform.

### 2. Dashboard Query Avalanche
The `/dashboard` route recalculates 7+ unindexed aggregates (`SUM` on `ProcurementItem` and `Expense`, `COUNT` on `User`, `Request`, and `FloorLendBorrow`, plus complex joins for `top_team_row`) synchronously on every load. Without caching, a tenant with 6 months of historical data will cause the Dashboard load time to degrade from ~100ms to several seconds.

### 3. Database Indexing Delusions
Despite the Architecture Guide claiming `floor` is indexed on all primary tables, `models.py` reveals that `floor` lacks indexes on critical tables like `Menu`, `Expense`, `TeaTask`, `Request`, and `ProcurementItem`. Because Flask's `g.tenant_id` global filter is appended to every query, PostgreSQL will perform costly sequential scans within a tenant’s dataset to resolve the `floor = user.floor` conditions.

### 4. Unbounded Calendar Payload Bloat
The `/calendar` route executes `Menu.query.all()`, `TeaTask.query.all()`, and `SpecialEvent.query.all()` without any date bounding (e.g., limiting to the current month). After a year in production, every calendar page refresh will serialize and transmit thousands of historical rows to the client browser, inflating memory usage and payload size linearly.

### 5. High-Risk Deployment Pipeline
The `.github/workflows/deploy.yml` runs `flask db upgrade` directly on the live production database via SSH. A failed Alembic migration will leave the schema in a corrupted, half-applied state, causing immediate platform-wide downtime with no automated rollback mechanism.

---

## PHASE 2 — MISSING FEATURES

### 1. Background Job Queue (Celery/RQ + Redis)
**Why:** Absolute necessity for offloading OCR image processing, bulk push notifications, and daily budget resets. Without it, the core web threads will choke under load.

### 2. Tenant-Level Audit Trails
**Why:** As operations grow, disputes will occur over who modified a budget, deleted an expense, or assigned a `Garamat` (penalty). The current `PlatformAudit` only tracks Super Admin actions. A tenant-level audit log is legally and operationally required for finance and admin accountability.

### 3. Application-Level Caching (Redis)
**Why:** To survive thousands of daily dashboard loads, the heavy `SUM` and `COUNT` queries must be cached and invalidated only when new expenses or requests are approved. 

### 4. Soft Deletes & Data Retention
**Why:** The database will bloat with stale `PushSubscription` tokens and completed `ProcurementItem` rows. Scheduled cron jobs to archive old data or remove dead push tokens are missing.

### 5. Rate Limiting
**Why:** Expensive endpoints like `/finance/expenses` (OCR upload) and authentication routes are completely exposed, risking DoS attacks or accidental resource exhaustion by double-clicking users.

---

## PHASE 3 — ROLE EXPERIENCE ISSUES

### MEMBER Perspective
*   **Frustration:** Application becomes noticeably sluggish. The Dashboard and Calendar take seconds to load. 
*   **Annoyance:** Notification fatigue. Every special event and announcement triggers a push notification. Members will disable browser notifications entirely because there is no granular "opt-out" preference center.

### PANTRY HEAD Perspective
*   **Frustration:** Uploading multiple receipts during procurement causes browser timeouts due to the synchronous OCR processing, forcing them to retry and accidentally create duplicate bills.
*   **Tedium:** Assigning daily `TeaTask` duties manually over 6 months becomes exhausting. They will desperately want a "recurring rotation" or "bulk auto-assign" feature.

### ADMIN Perspective
*   **Frustration:** When a Pantry Head leaves the company or moves floors, reassigning their pending tasks, menus, and budgets is a nightmare because there are no bulk action tools. 
*   **Limitation:** The rigid `user.floor` integer makes it impossible for an Admin to easily assign a temporary floating manager to cover multiple floors.

### SUPER ADMIN Perspective
*   **Frustration:** No tenant health metrics or usage graphs exist. Deleting a bad actor tenant is dangerous because the lack of comprehensive cascading deletes might leave orphaned blobs (like receipt images) or lock the database during manual deletion.

---

## PHASE 4 — DATABASE FUTURE

### 1. Composite Indexing strategy
Introduction of `(tenant_id, floor)` composite indexes is required immediately for `Menu`, `ProcurementItem`, `Request`, and `TeaTask` to support fast read operations on tenant-specific floor dashboards.

### 2. Device Registry Normalization
`PushSubscription` currently links directly to a user. This table will bloat with stale tokens as users upgrade phones or clear browser caches. It must be normalized to track `device_id` and `last_active_at` to prune dead endpoints efficiently.

### 3. Table Partitioning
As historical data grows, tables like `Expense`, `Menu`, and `Feedback` should be partitioned by year or `tenant_id` at the PostgreSQL level to maintain index sizes in RAM.

### 4. Archiving Strategy
Movement of completed `ProcurementItem`, `TeaTask`, and `Request` rows older than 6 months to a historical read-only schema to keep operational tables lean.

---

## PHASE 5 — API FUTURE

### 1. Headless REST/GraphQL APIs
As tenants demand native iOS/Android mobile apps, the tightly coupled Jinja templates will become a bottleneck. The application must evolve to provide standardized JSON endpoints.

### 2. JWT Authentication
Transitioning from stateful Flask sessions (which are difficult to scale across multiple servers or mobile apps) to stateless JWTs to support mobile edge caching and robust cross-platform auth.

### 3. Webhooks & Export APIs
Tenants will require integrations: Slack/Discord webhooks for `Request` approvals, and CSV/API exports of `Bill` and `Expense` data to accounting software like Xero or QuickBooks.

### 4. Bulk Action Endpoints
Admins will require APIs to mass-approve requests, mass-assign menus, and cleanly offboard users.

---

## PHASE 6 — PERFORMANCE RISKS

1.  **`/calendar` Route (CRITICAL):** Unbounded `.all()` queries fetching historical data indefinitely.
2.  **`/dashboard` Route (CRITICAL):** Multiple synchronous aggregates (`SUM`, `COUNT`) without a caching layer.
3.  **OCR Processing in `/finance/expenses` (HIGH):** Synchronous execution locking WSGI workers and spiking VM CPU.
4.  **Missing `floor` Indexes (HIGH):** Causing slow sequential scans on multi-tenant tables.
5.  **Push Notification Dispatch (MEDIUM):** Synchronous HTTP calls to FCM/Mozilla stalling the application during announcements.

---

## PHASE 7 — SECURITY FUTURE

### 1. Missing CSRF Protection
Currently absent (`Flask-WTF` is not utilized). This makes the authenticated web app highly vulnerable to Cross-Site Request Forgery, allowing attackers to trick admins into approving budgets or modifying users.

### 2. Granular Permission Scopes
Hardcoded strings (`user.role in ['admin', 'pantryHead']`) will fail as the SaaS scales. Custom roles with granular boolean scopes (e.g., `can_approve_expense`, `can_manage_tea`) must be implemented to support diverse tenant organizational structures.

### 3. Session Hardening & Device Management
Users currently cannot "Log out from all devices" or view active sessions, posing a risk if a member's device is compromised.

### 4. Abuse Prevention
Strict rate limiting is required on the OCR upload endpoint to prevent a malicious user from intentionally OOMing (Out of Memory) the server by uploading massive PDFs continuously.

---

## PHASE 8 — DEVOPS FUTURE

### 1. Staging Environment & Database Backups
Deployments cannot happen directly on the primary VM. The CI/CD pipeline must include an automated `pg_dump` backup step prior to executing Alembic upgrades to prevent catastrophic data loss.

### 2. Zero-Downtime Deployments (Blue/Green)
Executing `systemctl restart gunicorn` drops active user requests. Nginx should be configured to seamlessly swap traffic between two Gunicorn sockets during deployment.

### 3. Log Rotation & Alerting
Gunicorn and Nginx logs on the small Oracle boot volume will fill the disk over 6 months, crashing the server. Log rotation and Prometheus/Grafana integrations are required to alert on worker saturation or high CPU usage.

### 4. Worker Node Splitting
The monolithic architecture must be split: one VM for the web server (Flask) and a separate VM for the Celery/RQ background worker handling OCR and notifications.

---

## PHASE 9 — SAAS FUTURE

### 1. Tenant Billing & Usage Quotas
Integrating Stripe to manage the `subscription_status` on the `Tenant` model. Implementing automated locking for unpaid accounts and limiting OCR receipt scans based on subscription tiers.

### 2. Self-Serve Onboarding Funnel
Transitioning from manual Super Admin provisioning to an automated sign-up flow where organizations can securely create and configure their own `tenant_id` and initial Admin account.

### 3. Tenant Dashboards (White-labeling)
Allowing organizations to upload custom logos, set primary interface colors, and map custom domains (e.g., `pantry.acmecorp.com`).

### 4. Global Analytics
Super Admins will need a macro-level dashboard showing DAU/MAU (Daily/Monthly Active Users), error rates per tenant, and feature adoption (e.g., "How many tenants actively use Lend/Borrow?").

---

## PHASE 10 — PRIORITY ROADMAP

### CRITICAL (Must be done before scaling - Next 30 Days)
*   **Calendar Pagination:** Add start/end date bounds to the `/calendar` route queries to prevent payload bloat.
*   **Background Jobs:** Move Tesseract OCR and `pywebpush` dispatch into a Celery/RQ worker queue.
*   **Database Indexes:** Add composite indexes for `(tenant_id, floor)` on all heavy operational tables (`Menu`, `ProcurementItem`, `Request`).
*   **Security:** Implement comprehensive CSRF protection across all state-mutating forms.

### HIGH (Needed within 3-6 months)
*   **Caching Layer:** Implement Redis caching for the `/dashboard` aggregate queries.
*   **DevOps Safety:** Update GitHub Actions to perform automated DB backups before migrations and implement graceful Gunicorn reloads.
*   **Rate Limiting:** Protect the OCR upload, Login, and push notification endpoints.
*   **Audit Logging:** Create a tenant-level Audit Log table for financial and administrative actions.

### MEDIUM (Future improvements - 6-12 months)
*   **API Decoupling:** Begin extracting Jinja views into standardized REST/JSON APIs to prepare for mobile app development.
*   **Admin Tools:** Implement bulk reassignment tools for Pantry Heads and Admins.
*   **User Preferences:** Add granular opt-out settings for member push notifications.

### LOW (Nice improvements - 12+ months)
*   **Automation:** Implement recurring scheduling algorithms for `TeaTask` rotation.
*   **Monetization:** Build the self-serve Stripe billing portal.
*   **Customization:** Enable custom white-labeling and domain mapping per tenant.