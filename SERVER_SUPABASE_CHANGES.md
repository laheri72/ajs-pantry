# Infrastructure & Database Change List

This document lists manual changes required on the production Ubuntu server and the Supabase PostgreSQL database to support the hardening phase.

## 🖥️ Ubuntu Server Changes

### 1. Environment Variable Hardening
Update the Systemd service file or `.env` to include missing secrets and remove fallbacks.
- **Action:** Add `INTERNAL_API_SECRET` (to replace `PANTRY_SECRET_123`).
- **Action:** Ensure `SESSION_SECRET` is a long, random string.
- **Command:** `sudo nano /etc/systemd/system/ajs-pantry.service` OR `nano /home/ubuntu/ajs-pantry/.env`

### 2. Dependency Prep (PostgreSQL)
Before switching from `psycopg2-binary` to `psycopg2`, the system requires build tools.
- **Action:** Install development headers.
- **Command:** `sudo apt install libpq-dev python3-dev gcc`

### 3. Database Migration Initialization
Move away from `db.create_all()`.
- **Action:** Initialize Flask-Migrate on the server (one-time).
- **Command:** 
  ```bash
  flask db init
  flask db migrate -m "initial migration"
  flask db upgrade
  ```

---

## 🗄️ Supabase / PostgreSQL Changes

### 1. Performance Indexing
Speed up tenant-scoped queries.
- **Action:** Ensure `tenant_id` and `floor` columns have B-Tree indexes on all major tables.
- **SQL:** `CREATE INDEX IF NOT EXISTS idx_menu_tenant_floor ON menu(tenant_id, floor);` (Apply to `procurement_item`, `tea_task`, etc.)

### 2. Row Level Security (RLS) Prep
Move from application-level isolation to database-level safety.
- **Action:** Research enabling RLS on the `public` schema.
- **Target:** All tables inheriting from `TenantMixin`.

### 3. Backup Strategy
- **Action:** Confirm Supabase automated backup frequency and retention policy.
