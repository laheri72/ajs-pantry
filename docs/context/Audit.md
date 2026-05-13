# 1. Executive Summary
AJS Pantry is feature-rich and structurally serious: modular Flask blueprints, tenant-scoped models, Redis/RQ workers, dashboard caching, Faculty budget workflows, OCR import, PWA notifications, and Supabase/Postgres migrations are all present.

Production readiness is **moderate, not high**. The strongest parts are domain coverage, tenant-aware ORM filtering, Faculty workflow maturity, and recent RQ/caching work. The biggest risks are security and operations: no CSRF, only partial rate limiting, hardcoded/default passwords, weak deployment rollback, limited audit coverage, direct production migrations, and several large “god” route/template files.

Overall: this is a capable internal operations platform that can run for a small/mid tenant set, but it is not yet hardened for hostile internet exposure or large multi-tenant scale.

# 2. Current Architecture Analysis
- Backend architecture: single Flask app in [app.py](</d:/My Sites/ajs-pantry/app.py:32>) with global app initialization, SQLAlchemy, Flask-Migrate, Redis/RQ, Flask-Caching, and blueprint registration.
- Blueprint organization: domain-based and mostly sensible: `auth`, `pantry`, `finance`, `ops`, `admin`, `faculty`, `super_admin`, `main`. The issue is size: `pantry/routes.py`, `faculty/routes.py`, `finance/routes.py`, and `expenses.html` are too large.
- Worker architecture: RQ queue `ajs_pantry_tasks` is initialized from `REDIS_URL`; if Redis fails, work falls back synchronously.
- Redis/RQ design: good first step, with queue health helpers and job polling. Missing retry/backoff policy, dead-letter workflow, idempotency keys, and operational alerting.
- OCR pipeline: upload -> MIME check -> temp file -> RQ worker -> `pdfplumber` or Tesseract -> parser factory -> JSON review -> bill save. Size guard exists, but content validation is shallow.
- Deployment architecture: GitHub Actions SSHes to Oracle, pulls `main`, installs requirements, runs `flask db upgrade`, restarts systemd. No staging, backup, smoke test, or rollback gate.
- Database flow: Postgres/Supabase via SQLAlchemy. Tenant isolation is enforced by `do_orm_execute` with `TenantMixin`, which is strong but invisible and easy to bypass with raw SQL.
- Frontend/backend interaction: Jinja-heavy, Bootstrap/vanilla JS, many `fetch()` JSON endpoints. No CSRF token pattern across forms/fetch calls.
- Async boundaries: OCR, push, and email are queue-capable; many admin/reporting actions remain synchronous.

# 3. Role-Based Experience Audit
Superadmin:
- Strong: tenant provisioning, tenant toggles, Faculty management, queue health, global dish catalog.
- Friction: tenant analytics are broad but not operationally actionable; no deploy/DB/backup status; no incident dashboard.
- Risk: platform-wide actions are powerful and CSRF-exposed.

Admin:
- Strong: floor switching, member management, reassignment, finance visibility.
- Friction: too many controls live in dense pages; reset password exposes a shared default; no granular audit trail for many actions.
- Scalability issue: admin dashboard loops over floors and runs repeated aggregate queries.

Faculty:
- Strong: most mature workflow: cycles, submissions, review, member import, member activation, meal insights.
- Friction: `/reports` living inside Faculty blueprint is conceptually confusing; import uses a fixed default password; report PDF storage still has legacy absolute-path support.
- Missing: stronger reporting analytics, reminder automation, review SLAs, per-action audit.

Pantry members:
- Strong: dashboard, calendar, requests, feedback/suggestions, push notifications.
- Friction: notification fatigue risk; offline/PWA logic is partly placeholder; profile picture logic stores locally, not server-side.
- Abuse risk: suggestions, feedback, and requests lack rate limits.

Staff/operators:
- Strong: procurement, tea tasks, bill recording, OCR import are practical.
- Friction: OCR failure recovery is mostly “retry/contact admin”; procurement and expenses pages are very dense; report generation flow is overloaded.

# 4. Security Audit
| Issue | Severity | Impact | Exploit scenario | Recommended fix |
|---|---:|---|---|---|
| No CSRF protection across POST forms/fetch calls | Critical | Authenticated state changes can be forced cross-site | Attacker gets an admin to visit a page that silently submits `/platform-admin/tenants/<id>/toggle` or `/bills/<id>/delete` | Add Flask-WTF/CSRFProtect or signed double-submit tokens for all POST/JSON routes |
| Hardcoded default admin creation | Critical | Possible platform-wide bypass account | [app.py](</d:/My Sites/ajs-pantry/app.py:148>) creates `Administrator` with password `administrator`; `tenant_id=None` is treated as global bypass | Remove startup user creation; require one-time CLI bootstrap with generated password |
| Shared onboarding password `maskan1447` | High | Account takeover window across imported users | Anyone knowing TR numbers can try default password before first login | Generate per-user temporary passwords or magic setup links; expire after first use |
| Partial rate limiting | Medium | Remaining abuse risk on non-V1 endpoints | V1 protects `/login`, `/staff-login`, `/faculty/login`, `/platform-admin/login`, and `/expenses/import-receipt`; internal email, notification dispatch, imports, push subscription, and other write/API endpoints are still open | Extend Flask-Limiter with IP/user/tenant scopes after V1 |
| Weak session hardening | High | Session theft impact higher | `SESSION_COOKIE_SECURE`, `SAMESITE`, trusted proxy settings not explicitly configured | Set Secure, HttpOnly, SameSite=Lax/Strict, ProxyFix, secure headers |
| Upload validation is extension/MIME based | High | Parser abuse, decompression bombs | Malicious PDF/image passes MIME and triggers expensive parsing | Verify magic bytes, image dimensions, PDF page count, timeouts, antivirus scan for PDFs |
| Internal email endpoint is single shared secret | High | Spam relay if secret leaks | `/internal/send-email` accepts HTML and sends synchronously with only `X-SECRET` | Use HMAC request signing, rate limit, allowlist callers, queue mail, sanitize/validate payload |
| Error leakage | Medium | Internal details exposed | Several JSON routes return `str(e)` | Return generic messages, log structured exception server-side |
| Push subscription lacks schema validation | Medium | DB bloat/spam vector | Authenticated user posts arbitrary endpoint/key payload repeatedly | Validate payload, unique endpoint index, cap devices/user, track last_seen |
| No MFA/device/session management | Medium | Privileged compromise persists | Superadmin/admin password stolen | Add MFA for superadmin/faculty/admin and “logout all sessions” |
| RLS enabled without visible policies | Medium | False sense of DB isolation | Supabase RLS migration enables RLS, but app isolation relies on ORM | Add explicit DB policies or document app role bypass model |

# 5. Database & Data Integrity Audit
- Table design is serviceable and tenant-aware. Most operational tables include `tenant_id` and useful composite indexes.
- Strong: `User.email` and `User.tr_number` are globally unique; Faculty report has `UniqueConstraint(cycle_id, floor)`.
- Weak: financial amounts mix `Float` on legacy `Expense.amount` with `Numeric` elsewhere. Standardize money on `Numeric`.
- Relationship quality: many FKs exist, but several deletes are manual rather than cascading consistently.
- Normalization: `PushSubscription` needs device identity, endpoint uniqueness, `last_active_at`, and invalidation metadata.
- Query efficiency: main dashboard is cached; admin/superadmin analytics still run many repeated aggregates and per-tenant/per-floor loops.
- Migration safety: live `flask db upgrade` is the largest DB risk. No preflight, lock timeout, backup, or rollback.
- Transaction safety: cycle/report deletion touches DB and filesystem in one logical operation without compensating recovery.
- Orphan risks: hard deletes for teams, reports, messages, requests, procurement, feedback can remove evidence and operational history.
- Missing indexes: add composite indexes for `tenant_audit_log(tenant_id, created_at)`, `faculty_budget_cycle(tenant_id, status)`, `faculty_report_submission(tenant_id, cycle_id, floor, status)`, `push_subscription(user_id, endpoint unique)`.
- Add archival/cleanup jobs for old procurement, requests, push tokens, temp receipts, archived bills, and stale reports.
- Expand soft delete beyond users: bills/reports/requests/procurement should prefer archive/void states for auditability.

# 6. Performance & Scalability Audit
- Redis usage is pragmatic but narrow: dashboard and Faculty dashboard only.
- Queue architecture prevents OCR from blocking most requests, but sync fallback can still overload web workers when Redis is down.
- OCR bottlenecks: Tesseract/PDF parsing is CPU-heavy; no page/image dimension limits; one queue handles all jobs.
- Polling: receipt status polling is acceptable at small scale; should use exponential backoff and visible worker health.
- Frontend rendering: `expenses.html` and `menus.html` are very large and do substantial DOM work with `innerHTML`.
- Worker scaling: one queue and one worker service is simple but limits prioritization. Email/push/OCR should be separate queues.
- Database hotspots: admin and superadmin dashboards; meal insights; people leaderboards; global dish reference counts.

Short-term:
- Rate limiting V1 is in place for auth and OCR bill upload; add upload parsing limits and expand rate limits to email/notifications/imports.
- Split RQ queues: `ocr`, `notifications`, `emails`.
- Add indexes listed above.
- Cache superadmin/admin aggregate dashboards.

Long-term:
- Move analytics to materialized summaries.
- Add async report generation.
- Introduce API/service layer and progressively reduce giant Jinja pages.
- Add tenant-level quotas for OCR, notifications, imports, and bulk operations.

# 7. DevOps & Deployment Audit
- GitHub Actions deploy is too direct: pull main, install, migrate, restart.
- No staging environment, no backup step, no migration dry-run, no smoke test, no health check gate.
- Worker service has `Restart=always`, which is good.
- No web systemd unit template in repo, only worker template.
- No observability stack: no Sentry, Prometheus, uptime checks, structured request logs, queue alerts, DB slow-query monitoring.
- No disaster recovery evidence: backups, restore drill, report-file backup, and Supabase PITR policy are undocumented.

Hardening:
- Add staging + manual approval for production.
- Run `pg_dump` or verified Supabase backup before migrations.
- Add `/healthz`, `/readyz`, `/queue-health`, DB ping, Redis ping.
- Deploy with release directories or tagged rollback.
- Alert on 5xx rate, worker count=0, queue age, failed jobs, Redis down, DB migration failure, disk usage, report storage errors.

# 8. Technical Debt & Code Quality Audit
- Oversized files: `templates/expenses.html` ~3k lines, `pantry/routes.py` ~1.8k, `faculty/routes.py` ~1.4k, `finance/routes.py` ~1k.
- Coupling: routes mix auth, validation, DB writes, notifications, parsing, rendering, and auditing.
- Worker boundary violations: sync fallback runs expensive OCR/email/push inline.
- Duplicate patterns: role checks, floor checks, flash/error handling, file path building, notification fanout.
- Error handling is inconsistent; several routes expose raw exception strings.
- Frontend uses many inline event handlers and large `innerHTML` blocks, increasing XSS/maintenance risk.

Ideal structure:
- `services/`: `authz`, `finance`, `faculty_cycles`, `reports`, `notifications`, `imports`.
- `repositories/` or query modules for dashboard/admin analytics.
- `tasks/`: separate RQ workers by queue.
- `forms/validators/`: shared validation and CSRF.
- `uploads/`: centralized safe file handling.
- `audit/`: mandatory audit wrappers for privileged mutations.

# 9. Feature Audit
Excellent:
- Tenant-aware architecture, Faculty budget/report workflow, OCR import, dashboard caching, queue health, PWA push, smart menu rotation, Excel import validation.

Redundant:
- `suggestions.html` remains after Feedbacks merge.
- Legacy expenses and new bills/report flow coexist with confusing overlap.
- Profile picture/local offline/export demo code appears non-production.

Unfinished:
- Offline IndexedDB sync, cooking reminders, local profile picture upload, monitoring, backup/restore, notification preferences.

Confusing:
- `/reports` inside Faculty blueprint but used by Admin/Pantry Head.
- “Super-admin dashboard” wording in tenant admin page.
- Faculty messages creation then per-recipient send flow.

Dangerous:
- Permanent deletes, default passwords, CSRF-exposed privileged routes, sync fallback for expensive jobs.

Underutilized:
- Tenant audit log, queue health data, meal insights, dish estimate intelligence.

Remove/simplify/merge:
- Remove stale standalone suggestions template if unused.
- Replace demo offline/profile/export code with real or no feature.
- Move reports into a neutral `reports` blueprint.
- Merge notification logic into one service with user preferences.

# 10. Missing Features & Strategic Opportunities
Quick wins:
- CSRF, rate limits, secure cookie headers.
- Notification preference center.
- Queue/DB health page for superadmin.
- Temp upload cleanup command/cron.
- Audit logging for finance/report/admin mutations.

High-impact:
- Admin analytics: budget burn rate, overdue reports, floor risk score.
- OCR improvements: confidence score, parser versioning, duplicate bill detection.
- Inventory intelligence: recurring item forecast, price anomaly detection, vendor trends.
- Fraud/anomaly detection: duplicate bills, unusual spend, report mismatch, repeated deletions.
- Reporting: monthly tenant pack, Faculty verification exports, immutable audit trails.

Long-term:
- PWA offline-first task completion.
- Native/mobile API boundary.
- Multi-queue worker fleet.
- Observability dashboard.
- Tenant quotas/billing and self-serve onboarding.

# 11. Production Readiness Score
- Architecture: 7/10
- Security: 4/10
- Scalability: 6/10
- Maintainability: 5/10
- Reliability: 5/10
- UX: 6/10
- Admin operations: 6/10
- Observability: 3/10
- Deployment maturity: 4/10
- Developer experience: 5/10

# 12. Priority Action Roadmap
Immediate fixes:
- Add CSRF everywhere. Reason: critical web exploit class. Impact: very high. Difficulty: medium. Risk: form regressions. Priority: P0.
- Remove hardcoded startup admin/default password patterns. Reason: privileged takeover risk. Impact: very high. Difficulty: low-medium. Risk: bootstrap process change. Priority: P0.
- Extend rate limiting beyond V1 to imports, internal email, notifications, push subscription, and other high-cost writes. Reason: spam/DoS. Impact: high. Difficulty: low. Risk: tuning false positives. Priority: P1.
- Secure cookies and headers. Reason: session hardening. Impact: high. Difficulty: low. Risk: proxy config mismatch. Priority: P0.
- Add production DB backup before migrations. Reason: rollback survival. Impact: high. Difficulty: medium. Risk: secret/storage setup. Priority: P0.

Short-term:
- Central upload validation service with magic-byte checks and parser limits. Priority: P1.
- Expand TenantAuditLog to finance, cycles, reports, admin role changes, deletes. Priority: P1.
- Split RQ queues and disable expensive sync fallback in production. Priority: P1.
- Normalize push subscriptions and add cleanup job. Priority: P1.
- Add health/readiness endpoints and queue alerts. Priority: P1.

Mid-term:
- Extract services from large route files. Priority: P2.
- Cache/admin analytics materialization. Priority: P2.
- Replace permanent deletes with archive/void states. Priority: P2.
- Move `/reports` to a dedicated reports blueprint. Priority: P2.

Long-term:
- Staging + blue/green or release-based deploys. Priority: P3.
- Observability stack with Sentry, metrics, logs, alerts. Priority: P3.
- API-first mobile/PWA evolution. Priority: P3.
- AI-assisted inventory/OCR/fraud intelligence with human review. Priority: P3.
