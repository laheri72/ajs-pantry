# AJS Pantry — Future Scalability & Evolution Audit
**Date:** February 28, 2026
**Focus:** 6–12 Month Production Growth Trajectory

---

## PHASE 1 — FUTURE RISKS

### 1. Synchronous External Dependencies Locking WSGI Workers
Currently, Tesseract OCR (`ParserFactory.process_receipt`) and Push Notifications (`pywebpush.webpush`) execute synchronously within the request-response cycle. As user activity scales, simultaneous receipt uploads or floor-wide announcements will block Gunicorn workers for seconds at a time. On an Oracle Free Tier ARM VM, this will rapidly exhaust the worker pool, causing `502 Bad Gateway` and `504 Gateway Timeout` errors across the entire platform.

### 2. Dashboard Query Avalanche
The `/dashboard` route recalculates 7+ unindexed aggregates (`SUM` on `ProcurementItem` and `Expense`, `COUNT` on `User`, `Request`, and `FloorLendBorrow`, plus complex joins for `top_team_row`) synchronously on every load. Without caching, a tenant with 6 months of historical data will cause the Dashboard load time to degrade from ~100ms to several seconds.

### 3. Database Indexing Delusions
Despite the Architecture Guide claiming `floor` is indexed on all primary tables, `models.py` reveals that `floor` lacks indexes on critical tables like `Menu`, `Expense`, `TeaTask`, `Request`, and `ProcurementItem`. Because Flask's `g.tenant_id` global filter is appended to every query, PostgreSQL will perform costly sequential scans within a tenant’s dataset to resolve the `floor = user.floor` conditions.

### 4. High-Risk Deployment Pipeline
The `.github/workflows/deploy.yml` runs `flask db upgrade` directly on the live production database via SSH. A failed Alembic migration will leave the schema in a corrupted, half-applied state, causing immediate platform-wide downtime with no automated rollback mechanism.

---

## PHASE 2 — MISSING FEATURES

### 1. Background Job Queue (Celery/RQ + Redis)
**Why:** Absolute necessity for offloading OCR image processing, bulk push notifications, and daily budget resets. Without it, the web threads will choke under load.

### 2. Tenant-Level Audit Trails
**Why:** As operations grow, disputes will occur over who modified a budget, deleted an expense, or assigned a `Garamat` (penalty). A tenant-level audit log is legally and operationally required for finance and admin accountability.

### 3. Application-Level Caching (Redis)
**Why:** To survive thousands of daily dashboard loads, the heavy `SUM` and `COUNT` queries must be cached and invalidated only when new expenses or requests are approved. 

### 4. Soft Deletes & Data Retention
**Why:** The database will bloat with stale `PushSubscription` tokens and completed `ProcurementItem` rows. Scheduled cron jobs to archive old data or remove dead push tokens are missing.

### 5. Rate Limiting
**Why:** Expensive endpoints like `/finance/expenses` (OCR upload) and authentication routes are completely exposed, risking DoS attacks or accidental resource exhaustion.

---

## PHASE 3 — ROLE EXPERIENCE ISSUES

### MEMBER Perspective
*   **Frustration:** Application becomes noticeably sluggish. The Dashboard takes seconds to load. 
*   **Annoyance:** Notification fatigue. Members will disable browser notifications because there is no granular "opt-out" preference center.

### PANTRY HEAD Perspective
*   **Frustration:** Uploading multiple receipts during procurement causes browser timeouts due to the synchronous OCR processing.
*   **Tedium:** While Menu management is now automated with "Smart Rotation," assigning daily `TeaTask` duties manually over 6 months remains exhausting. They will want a similar "recurring rotation" for tea.

### ADMIN Perspective
*   **Frustration:** When a Pantry Head leaves, reassigning their pending tasks and budgets is difficult because there are no bulk reassignment tools. 

### SUPER ADMIN Perspective
*   **Frustration:** No tenant health metrics or usage graphs exist. 

---

## PHASE 4 — DATABASE FUTURE

### 1. Composite Indexing strategy
Introduction of `(tenant_id, floor)` composite indexes is required immediately for `Menu`, `ProcurementItem`, `Request`, and `TeaTask` to support fast read operations.

### 2. Device Registry Normalization
`PushSubscription` currently links directly to a user. This table will bloat with stale tokens. It must be normalized to track `device_id` and `last_active_at`.

### 3. Table Partitioning
Tables like `Expense`, `Menu`, and `Feedback` should be partitioned by year or `tenant_id` at the PostgreSQL level.

### 4. Archiving Strategy
Movement of completed `ProcurementItem`, `TeaTask`, and `Request` rows older than 6 months to a historical read-only schema.

---

## PHASE 5 — API FUTURE

### 1. Headless REST/GraphQL APIs
As tenants demand native iOS/Android mobile apps, the tightly coupled Jinja templates will become a bottleneck. 

### 2. JWT Authentication
Transitioning from stateful Flask sessions to stateless JWTs to support mobile edge caching and robust cross-platform auth.

### 3. Webhooks & Advanced Integrations
Slack/Discord webhooks for `Request` approvals, and API exports of financial data to accounting software.

---

## PHASE 6 — PERFORMANCE RISKS

1.  **`/dashboard` Route (CRITICAL):** Multiple synchronous aggregates (`SUM`, `COUNT`) without a caching layer.
2.  **OCR Processing (HIGH):** Synchronous execution locking WSGI workers and spiking VM CPU.
3.  **Missing `floor` Indexes (HIGH):** Causing slow sequential scans on multi-tenant tables.
4.  **Push Notification Dispatch (MEDIUM):** Synchronous HTTP calls stalling the application during announcements.

---

## PHASE 7 — SECURITY FUTURE

### 1. Missing CSRF Protection
Currently absent. This makes the authenticated web app vulnerable to Cross-Site Request Forgery.

### 2. Granular Permission Scopes
Hardcoded strings (`user.role in ['admin', 'pantryHead']`) will fail as the SaaS scales. Custom roles with granular scopes must be implemented.

### 3. Session Hardening & Device Management
Users currently cannot "Log out from all devices" or view active sessions.

---

## PHASE 8 — DEVOPS FUTURE

### 1. Staging Environment & Database Backups
Deployments cannot happen directly on the primary VM. The CI/CD pipeline must include an automated `pg_dump` backup step.

### 2. Zero-Downtime Deployments (Blue/Green)
Executing `systemctl restart gunicorn` drops active user requests. 

---

## PHASE 9 — SAAS FUTURE

### 1. Tenant Billing & Usage Quotas
Integrating Stripe to manage the `subscription_status` on the `Tenant` model. 

### 2. Self-Serve Onboarding Funnel
Transitioning from manual Super Admin provisioning to an automated sign-up flow.

### 3. Global Analytics
Super Admins will need a macro-level dashboard showing DAU/MAU and feature adoption.

---

## PHASE 10 — PRIORITY ROADMAP

### CRITICAL (Next 30 Days)
*   **Background Jobs:** Move Tesseract OCR and `pywebpush` dispatch into a Celery/RQ worker queue.
*   **Database Indexes:** Add composite indexes for `(tenant_id, floor)` on all heavy operational tables.
*   **Security:** Implement comprehensive CSRF protection.

### HIGH (3-6 Months)
*   **Caching Layer:** Implement Redis caching for the `/dashboard` aggregate queries.
*   **Audit Logging:** Create a tenant-level Audit Log table.
*   **Tea Rotation:** Implement "Smart Rotation" logic for `TeaTask` to match the Menu system.

### MEDIUM (6-12 Months)
*   **API Decoupling:** Begin extracting Jinja views into standardized REST/JSON APIs.
*   **Admin Tools:** Implement bulk reassignment tools for Pantry Heads and Admins.

### ACHIEVED MILESTONES (Completed April 2026)
*   [x] **Background Job Queue:** Moved Tesseract OCR, Push Notifications, and Email dispatch into an RQ (Redis Queue) worker system to prevent WSGI worker locking.
*   [x] **Dashboard Query Optimization:** Implemented Redis caching (Flask-Caching) for the heavy stats on the `/dashboard` route with smart invalidation.
*   [x] **Database Indexes:** Added composite indexes for `(tenant_id, floor)` on all heavy operational tables (Expense, ProcurementItem, Request, TeaTask, etc.).
*   [x] **Calendar Data Bounding:** The `/calendar` route now uses `start_bound` and `end_bound` to limit payload size.
*   [x] **Financial Export:** Admins can now export expense reports to Excel (CSV).
*   [x] **Menu Intelligence:** Implemented "Global Dish Library," "Dish Insights," and "One-Row Menu Model."
*   [x] **Menu Automation:** Implemented "Smart Rotation" (with absence conflict checks) and "Weekly Batch Planner."
*   [x] **Bulk Actions:** Added "Bulk Completion" for procurement items.
*   [x] **Contextual Feedback:** Linked suggestions directly to the Dish Library.