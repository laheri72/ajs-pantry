# AJS Pantry — System Architecture & Developer Guide

## 1. Overview

AJS Pantry is a multi-tenant Flask web application used to manage pantry operations (menus, tea tasks, expenses, feedback, procurement) across multiple residential or office floors.

The system provides **role-based access control** with four primary roles:

* Admin
* Pantry Head
* Tea Manager
* Member

---

## 2. Production Architecture

**Live stack:**

User → Firebase Hosting Domain → HTTPS (Let’s Encrypt)
→ Nginx Reverse Proxy (Oracle Cloud VM)
→ Gunicorn WSGI Server → Flask Application
→ Supabase PostgreSQL Database

Key properties:

* Public HTTPS access
* 24/7 Oracle Always-Free VM
* Automatic SSL renewal
* GitHub Actions CI/CD auto-deployment
* Supabase managed database hosting

---

## 3. Tech Stack

* **Backend:** Flask (Python 3.10+)
* **ORM:** Flask-SQLAlchemy
* **Database:** PostgreSQL (Supabase)
* **Driver:** psycopg2-binary
* **Frontend:** Jinja2 templates + vanilla CSS/JS
* **Server:** Gunicorn (production), Werkzeug (development)
* **Reverse Proxy:** Nginx
* **Hosting:** Oracle Cloud Always-Free VM
* **CI/CD:** GitHub Actions auto-deploy via SSH

---

## 4. Core File Structure

* `app.py` → Flask initialization, DB config, production boot
* `routes.py` → All HTTP routes and business logic
* `models.py` → SQLAlchemy schema definitions
* `main.py` → Local development runner
* `templates/` → Jinja HTML views
* `static/` → CSS, JS, assets
* `.github/workflows/deploy.yml` → CI/CD deployment pipeline

---

## 5. Local Development

### Setup

Create `.env`:

```
DATABASE_URL=postgresql://...
SESSION_SECRET=...
```

Install dependencies:

```
pip install -r requirements.txt
```

Run locally:

```
python main.py
```

---

## 6. Production Deployment

Gunicorn service runs via systemd:

```
gunicorn --bind 0.0.0.0:8000 app:app
```

Nginx handles:

* HTTPS termination
* Reverse proxy to Gunicorn
* Domain routing

Deployment is **fully automated**:

```
git push → GitHub Actions → Oracle VM → restart service
```

---

## 7. Authentication Model

* Session-based login using secure cookies
* Password hashing via Werkzeug
* Role-based authorization
* Multiple concurrent sessions currently allowed

Future improvement:

* DB-tracked sessions
* forced single login
* audit logging

---

## 8. Database Management

* Supabase PostgreSQL is the **single source of truth**
* Schema managed via SQLAlchemy models + manual SQL when required
* No full Alembic migration pipeline yet

---

## 9. Security Rules

* `.env` and secrets must never be committed
* Only HTTPS public access allowed
* Server access restricted via SSH keys
* CI/CD uses encrypted GitHub secrets

---

## 10. Testing Status

* No automated test suite yet
* Future plan: pytest + basic integration tests

---

## 11. Operational Notes

* Oracle VM is Always-Free and runs continuously
* SSL renews automatically via Certbot
* Supabase provides managed backups and uptime

---

## 12. Future Roadmap

* Session management in DB
* Automated database backups
* Admin analytics dashboard
* Performance scaling for 400+ users
* Full test coverage

