# AJS Pantry — Hardening & Security Tracker

This document tracks the implementation of security fixes, performance optimizations, and architectural hardening as identified in the System Audit (`security_logs.md`).

## Status Overview
- **System Health Score:** 95/100 (Current)
- **Remaining Critical Issues:** 0
- **Remaining High Issues:** 0

---

## 🟢 Priority 1: Critical (Immediate)
| Task ID | Description | Status | Target File(s) |
|:---:|:---|:---:|:---|
| P1-01 | Remove hardcoded `PANTRY_SECRET_123` from email route | ✅ Completed | `app.py` |
| P1-02 | Remove fallback for `SESSION_SECRET` | ✅ Completed | `app.py` |

## 🟡 Priority 2: High (Short-Term)
| Task ID | Description | Status | Target File(s) |
|:---:|:---|:---:|:---|
| P2-01 | Remove `db.create_all()` and move to Flask-Migrate | ✅ Completed | `app.py` |
| P2-02 | Implement global SQLAlchemy tenant isolation | ✅ Completed | `models.py`, `utils.py` |

## 🔵 Priority 3: Medium (Optimization)
| Task ID | Description | Status | Target File(s) |
|:---:|:---|:---:|:---|
| P3-01 | Fix N+1 queries in Dashboard/People with `joinedload` | ✅ Completed | `blueprints/pantry/routes.py` |
| P3-02 | Sync `pyproject.toml` and `requirements.txt` | ✅ Completed | Root files |
| P3-03 | Transition `psycopg2-binary` to `psycopg2` | ✅ Completed | `requirements.txt` |

## ⚪ Priority 4: Low (Cleanup)
| Task ID | Description | Status | Target File(s) |
|:---:|:---|:---:|:---|
| P4-01 | Adjust production logging levels (DEBUG -> INFO) | ✅ Completed | `app.py` |
| P4-02 | Remove `app.run(debug=True)` entry point | ✅ Completed | `app.py` |

---

## Change Log
### 2026-02-24
- **P1-01:** Migrated hardcoded email API secret to `INTERNAL_API_SECRET` environment variable.
- **P1-02:** Removed insecure fallback for `SESSION_SECRET`; app now strictly requires it to boot.
- **P2-01:** Integrated Flask-Migrate and removed `db.create_all()` to prevent multi-worker race conditions.
- **P2-02:** Implemented global multi-tenant isolation using SQLAlchemy `do_orm_execute` events. Every query is now automatically scoped to the current tenant without manual filtering.
- **P3-01:** Optimized core routes (Dashboard, People, Calendar) using SQLAlchemy `joinedload` to eliminate N+1 query overhead.
- **P3-02/03:** Standardized dependencies by syncing `pyproject.toml` and switching to production-ready `psycopg2`.
- **P4-01/02:** Hardened production entry point by removing debug execution and lowering log verbosity.
