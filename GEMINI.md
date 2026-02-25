# AJS Pantry — System Architecture & Developer Guide

## 1. Overview

AJS Pantry is a production-hardened, multi-tenant Flask web application designed to manage pantry operations (menus, tea tasks, expenses, feedback, procurement) across multiple residential or office floors.

The system provides **role-based access control (RBAC)** with five primary roles:
*   **Super Admin:** Platform-level management and tenant provisioning.
*   **Admin:** System-wide management for a specific tenant.
*   **Pantry Head:** Floor-level management (Menus, Procurement, Penalties).
*   **Tea Manager:** Specialized floor role for tea duty scheduling.
*   **Member:** General user with access to personalized feeds and feedback.

---

## 2. Production Architecture

**Live Stack:**
User → Firebase Hosting Domain → HTTPS (Let’s Encrypt)
→ Nginx Reverse Proxy (Oracle Cloud VM)
→ Gunicorn WSGI Server → Flask Application (Modular Blueprints)
→ Supabase PostgreSQL Database

**Key Properties:**
*   **Public HTTPS:** Managed via Nginx and Let's Encrypt.
*   **Compute:** Oracle Always-Free ARM VM (Continuous uptime).
*   **CI/CD:** Fully automated via GitHub Actions (SSH deployment + Auto-migrations).
*   **Persistence:** Supabase managed PostgreSQL with Row-Level Isolation logic.

---

## 3. Tech Stack

*   **Backend:** Flask 3.1.x (Python 3.11+)
*   **ORM:** Flask-SQLAlchemy + SQLAlchemy 2.0 (with global event listeners).
*   **Migrations:** Flask-Migrate (Alembic) for safe, versioned schema updates.
*   **Database:** PostgreSQL (Supabase) using the production-ready `psycopg2` driver.
*   **Frontend:** Jinja2 Templates + Vanilla CSS/JS + Bootstrap 5.
*   **PWA:** Service Worker support with Web Push Notifications (`pywebpush`).
*   **OCR:** Tesseract OCR for receipt scanning and automated expense entry.

---

## 4. Core File Structure (Modularized)

*   `app.py` → Factory initialization, Blueprint registration, and global middleware.
*   `models.py` → SQLAlchemy schema definitions + **Global Tenant Isolation Listener**.
*   `blueprints/` → Domain-driven logic:
    *   `auth/` → Session management and user security.
    *   `pantry/` → Menus, Calendar, Dishes, and Community Board.
    *   `finance/` → Expenses, Bills, Budgets, and Receipt OCR.
    *   `ops/` → Tea Tasks, Procurement, and User Requests.
    *   `admin/` → PH/Admin controls, Teams, and Penalties.
    *   `super_admin/` → SaaS Platform management.
*   `migrations/` → DB version history (managed via `flask db`).
*   `static/` → PWA assets, dark theme overrides, and core `script.js`.
*   `templates/` → Organized Jinja2 views matching blueprint domains.

---

## 5. Multi-Tenancy & Security

### 5.1 Global Tenant Isolation
Isolation is enforced at the **SQLAlchemy ORM level**. A `do_orm_execute` listener in `models.py` automatically injects `tenant_id == g.tenant_id` into every query for models inheriting from `TenantMixin`. This prevents data leakage even if a developer forgets a manual filter.

### 5.2 Environment Hardening
*   **Strict Boot:** The app will fail to start if `SESSION_SECRET` or `INTERNAL_API_SECRET` are missing.
*   **Credential Protection:** `.env` is ignored by Git; secrets are managed via server-side environment variables.
*   **RBAC Middleware:** `enforce_tenancy` and `_require_user` helpers validate every request context.

---

## 6. Automated Workflows

### 6.1 Deployment (CI/CD)
Pushing to `main` triggers `.github/workflows/deploy.yml`:
1.  Connects to Oracle VM via SSH.
2.  Pulls latest code.
3.  Installs dependencies from `requirements.txt`.
4.  **Auto-executes `flask db upgrade`** to sync Supabase.
5.  Restarts Gunicorn.

### 6.2 Push Notifications
Integrated PWA Push system using VAPID keys. Notifications are triggered server-side for:
*   New floor announcements/special events.
*   Assignment of Menus, Tea Duty, or Procurement tasks.
*   Request status updates (Approve/Reject).

---

## 7. Performance Standards

*   **N+1 Prevention:** Core routes (`Dashboard`, `People`, `Calendar`) must use `joinedload` for related entities (Users, Teams, Dishes).
*   **DB Indexing:** `tenant_id` and `floor` are indexed on all primary tables to ensure sub-100ms response times.
*   **Logging:** Level set to `INFO` in production to prevent disk bloat while maintaining auditability.

---

## 8. Maintenance Guidelines

*   **Schema Changes:** 
    1.  Update `models.py`.
    2.  Run `flask db migrate -m "description"` locally.
    3.  Commit the new migration file.
    4.  Push to deploy (Auto-upgrades Supabase).
*   **New Routes:** Always place routes in the relevant Blueprint and verify the `ROUTE_MAP.md` is updated.
*   **Dependencies:** Keep `pyproject.toml` and `requirements.txt` in sync. Use `psycopg2` (not -binary) for production stability.
