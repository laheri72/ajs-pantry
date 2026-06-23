# Project Memory & Behavioral Rules: Expense & Faculty Modules

This project-scoped rule file lists crucial architectural, logic, and dependency rules compiled from the [docs](file:///D:/My%20Sites/ajs-pantry/docs/context/) and source code for the AJS Pantry SaaS application. Refer to this memory during tasks related to the **Expense** and **Faculty** subsystems.

---

## 1. Context & Architecture Overview

AJS Pantry is a multi-tenant SaaS hostel pantry application using Flask, SQLAlchemy (Postgres via Supabase), Jinja2, Vanilla JS/CSS, and Redis/RQ queues.
*   **Tenancy Isolation:** Applied transparently at the ORM layer. Any model subclassing `TenantMixin` in [models.py](file:///D:/My%20Sites/ajs-pantry/models.py) automatically filters queries by `tenant_id = g.tenant_id` via a `do_orm_execute` event listener.
*   **Active Roles:** `super_admin`, `faculty`, `admin`, `pantryHead`, `teaManager`, `member`.
*   **Terminology Mapping:** The UI maps the DB term **Team** to **Room**, and **TeamMember** to **Member** using [terms.py](file:///D:/My%20Sites/ajs-pantry/config/terms.py).

---

## 2. Faculty Workflow Memory

The Faculty subsystem serves as the tenant-wide office management layer.

### 2.1 Budget Cycles & Allocations
*   **Models:** [FacultyBudgetCycle](file:///D:/My%20Sites/ajs-pantry/models.py#L358) and [Budget](file:///D:/My%20Sites/ajs-pantry/models.py#L338).
*   **Active Cycle Constraint:** Only one active budget cycle (`status='active'`) is allowed per tenant at any time.
*   **Budget Rows:** Created under [Budget](file:///D:/My%20Sites/ajs-pantry/models.py#L338) with `cycle_id` referencing the budget cycle and `is_faculty_allocation = True`.
*   **Visibility:** Budgets belonging to a cycle are visible to floors (Pantry Heads/Admins) *only* if the cycle status is not `'draft'`. Managed by `visible_budget_condition()` in [utils.py](file:///D:/My%20Sites/ajs-pantry/blueprints/utils.py).
*   **Deletes:** Deleting a cycle cascades using `_delete_cycle_related_data` in [routes.py](file:///D:/My%20Sites/ajs-pantry/blueprints/faculty/routes.py) which cleans up budgets, submission records, generated PDFs, and clears `Bill.report_submission_id`.

### 2.2 Report Submissions & PDFs
*   **Models:** [FacultyReportSubmission](file:///D:/My%20Sites/ajs-pantry/models.py#L377) and [ExpensePrintReport](file:///D:/My%20Sites/ajs-pantry/models.py#L409).
*   **Submission flow:** 
    1.  Admin/Pantry Head generate a combined PDF of selected bills from the Expenses wizard.
    2.  This generates an [ExpensePrintReport](file:///D:/My%20Sites/ajs-pantry/models.py#L409) record.
    3.  Under the floor-side reports page at [/reports](file:///D:/My%20Sites/ajs-pantry/blueprints/faculty/routes.py#L46), the PDF is uploaded and linked to the active cycle, creating a [FacultyReportSubmission](file:///D:/My%20Sites/ajs-pantry/models.py#L377).
*   **Auth Guard Exception:** Routes [/reports](file:///D:/My%20Sites/ajs-pantry/blueprints/faculty/routes.py#L46) and `/reports/<id>/download` live in the Faculty blueprint but are accessible to floor admins/pantry heads. Excluded from faculty-only enforcement via the `shared_staff_endpoints` set in [app.py](file:///D:/My%20Sites/ajs-pantry/app.py) and [routes.py](file:///D:/My%20Sites/ajs-pantry/blueprints/faculty/routes.py).
*   **Storage Path Risk:** Stored in `REPORT_STORAGE_ROOT` (`~/ajs-pantry-data/reports`). Currently, `FacultyReportSubmission.storage_path` saves absolute server paths, making uploads from local dev using the production DB problematic (uses Windows vs. Linux paths). 

### 2.3 User Directory & Excel Imports
*   **Active-User Filter:** Faculty reviews only active non-admin users (`role NOT IN ('admin', 'super_admin')` and `is_active = True`). Canonical helper is `faculty_visible_users_query()` in [utils.py](file:///D:/My%20Sites/ajs-pantry/blueprints/utils.py).
*   **Role management:** Faculty can promote or demote members to/from `pantryHead` or `teaManager`.
*   **Excel Onboarding:** Handled via routes `validate_import` and `commit_import` using `openpyxl`. Expected headers: `TR`, `Name`, `Floor`. Imported users receive default password `maskan1447` and `is_first_login = True`. Emails are auto-generated as `{TR}@jameasaifiyah.edu`.

---

## 3. Expense & Finance Memory

The finance subsystem tracks bills, OCR imports, and calculates floor ledger balances.

### 3.1 Budget Ledger Engine
*   **Core Function:** `build_floor_budget_ledger()` in [budgeting.py](file:///D:/My%20Sites/ajs-pantry/blueprints/budgeting.py#L82) is the central ledger balance engine.
*   **Calculation Logic:**
    1.  Fetches all budgets matching the floor, sorted chronologically.
    2.  Builds periods containing: opening balance, allocated amount, spent amount (bills + legacy expenses), and closing balance.
    3.  Identifies the `current_period` (the active cycle allocation, or the latest manual allocation).
    4.  Accumulates running balance forward from historical periods.
    5.  Returns a dictionary containing `current_available_budget`, `current_spent_amount`, `current_remaining_balance`, and `carryforward_balance`.

### 3.2 Bill vs. Expense Models
*   **Expense (Legacy):** [Expense](file:///D:/My%20Sites/ajs-pantry/models.py#L178) table contains legacy flat-file records using `Float` for amounts.
*   **Bill (Modern):** [Bill](file:///D:/My%20Sites/ajs-pantry/models.py#L271) contains production bills using `Numeric(12, 2)` linked to [ProcurementItem](file:///D:/My%20Sites/ajs-pantry/models.py#L290) entries. Future work should continue standardizing financials on `Numeric`.
*   **Bill Reconciliation:** `/reconcile/atomic/full` combines bill creation, new item procurement, and status updates atomically.

### 3.3 OCR & Rate Limiting
*   **OCR Pipeline:** Uploaded receipts are processed asynchronously using an RQ queue worker (SimpleCache sync fallback if Redis is down) via Tesseract/pdfplumber. The client polls the status of the OCR task.
*   **Limiter:** `Flask-Limiter` protects OCR upload endpoints and login views. Additional write endpoints remain unthrottled in V1.

---

## 4. Key References from Documentation

For deeper details, consult the original document files directly:
1.  [AI_CONTEXT.md](file:///D:/My%20Sites/ajs-pantry/docs/context/AI_CONTEXT.md) - Deep repository details, models, architecture patterns, and conventions.
2.  [FACULTY_REVAMP_MEMORY.md](file:///D:/My%20Sites/ajs-pantry/docs/context/FACULTY_REVAMP_MEMORY.md) - Faculty portal onboarding, auth rules, PDF mapping, and mobile layout notes.
3.  [Audit.md](file:///D:/My%20Sites/ajs-pantry/docs/context/Audit.md) - Full security, performance, database, and operational audit.
4.  [GEMINI.md](file:///D:/My%20Sites/ajs-pantry/docs/context/GEMINI.md) - High-level developer guidelines and schema change routines.
5.  [ROUTE_MAP.md](file:///D:/My%20Sites/ajs-pantry/docs/context/ROUTE_MAP.md) - Complete route list, request method mapping, and handler functions.
6.  [architecture_evolution_audit.md](file:///D:/My%20Sites/ajs-pantry/docs/context/architecture_evolution_audit.md) - Production priorities and developmental milestones.
7.  [DOCS_SEO_REDIRECTION.md](file:///D:/My%20Sites/ajs-pantry/docs/context/DOCS_SEO_REDIRECTION.md) - Google Search Console / Firebase hosting redirect setup.
