# Faculty Revamp Memory Context

Last updated: 2026-04-06

This file is the high-signal memory guide for the Faculty rollout and the follow-up UX/auth/storage changes that landed with it. Use this before searching the repo.

---

## 1. What Changed

The app now has a full Faculty workflow parallel to the existing tenant and super-admin flows.

Main outcome:
- `faculty` is now a first-class tenant-scoped role.
- Faculty manages tenant-wide budget cycles.
- Each cycle has one shared term and one shared report deadline.
- Each floor gets its own allocated budget and its own Faculty note.
- Pantry Head/Admin no longer allocate budgets from the Expenses page.
- Pantry Head/Admin still create bills and generate the combined report PDF from Expenses.
- That final PDF is submitted from the new `Reports` page for Faculty review.
- Faculty verifies/rejects report submissions and can release the next funding cycle.

Related UX cleanup:
- `Suggestions` and `Feedbacks` were merged into one `Feedbacks` page at the UI level.
- Faculty portal now has a mobile-responsive layout with an off-canvas menu.

---

## 2. Core Data Model Changes

Primary model updates live in `models.py`.

### New / expanded role model
- `User.role` now includes `faculty`.
- Faculty users are tenant-bound but not floor-bound.
- Faculty accounts should use `floor = NULL`.

### Budget cycle model
- `FacultyBudgetCycle`
  - Tenant-scoped cycle record
  - Shared term: `start_date`, `end_date`
  - Shared `submission_deadline`
  - `status` is one of `draft`, `active`, `closed`
  - `notes`, `created_by_id`, timestamps

### Budget model extensions
- `Budget` is now the authoritative per-floor allocation record.
- Important fields:
  - `cycle_id`
  - `allocated_by_id`
  - `faculty_note`
  - `is_faculty_allocation`
- Old PH/manual budgets still exist as `Budget` rows where `cycle_id IS NULL`.
- New Faculty-created budget rows usually have `cycle_id` set and `is_faculty_allocation = true`.

### Report submission model
- `FacultyReportSubmission`
  - One row per floor submission for a cycle
  - Stores:
    - `cycle_id`
    - `print_report_id`
    - `floor`
    - `uploaded_by_id`
    - `status` = `submitted`, `verified`, `rejected`
    - `report_title`
    - `submission_notes`
    - `review_notes`
    - `stored_filename`
    - `storage_path`
    - `file_size_bytes`
    - `revision_no`
    - `submitted_at`, `verified_at`, `verified_by_id`

### Saved print report models
- `ExpensePrintReport`
- `ExpensePrintReportBill`

These persist the result of the Expenses "Create Report" workflow so the Reports page can reference a saved report definition instead of manually re-selecting bills.

### Linked bill / expense references
- `Bill.report_submission_id`
- `Expense.report_submission_id`

In current usage:
- Bills are actively linked to Faculty submissions.
- Legacy expense linkage still exists in schema, but the current Reports UI no longer uses legacy expenses.

---

## 3. How the Faculty Workflow Works End-to-End

### A. Provisioning
- Super Admin provisions Faculty users from the tenant page.
- More than one Faculty user per tenant is allowed now.
- Faculty accounts are managed by Super Admin, not tenant Admin.

Main code:
- `blueprints/super_admin/routes.py`
- `templates/super_admin/tenant_view.html`

### B. Faculty login and portal
- Separate login page: `/faculty/login`
- Separate layout and visual shell under `templates/faculty/`

Main code:
- `blueprints/faculty/routes.py`
- `templates/faculty/base.html`
- `templates/faculty/login.html`

### C. Budget cycles
- Faculty creates a cycle in `/faculty/cycles`
- One shared date range and submission deadline
- One allocation row per floor
- One Faculty note per floor
- Cycle can be:
  - saved as draft
  - activated
  - closed
  - deleted

### D. Expenses and print reports
- Admin / Pantry Head still use `Expenses` for bills and report generation.
- The old floor-side budget add/delete routes are blocked.
- The print workflow now saves a real `ExpensePrintReport` record.

Main code:
- `blueprints/finance/routes.py`
- `templates/expenses.html`

### E. Report submission
- Floor-side page: `/reports`
- Allowed roles: `admin`, `pantryHead`
- User uploads exactly one combined PDF produced from Expenses
- User selects one saved print report
- Bills from that print report are linked to the submission

Main code:
- `blueprints/faculty/routes.py`
- `templates/reports.html`

### F. Faculty review
- Faculty opens cycle detail and then report detail
- Faculty can:
  - download the PDF
  - see linked bills
  - verify
  - reject with notes

Main code:
- `templates/faculty/cycle_detail.html`
- `templates/faculty/report_detail.html`

---

## 4. Important Route Memory

### Faculty portal routes
- `/faculty/login`
- `/faculty/dashboard`
- `/faculty/profile`
- `/faculty/cycles`
- `/faculty/cycles/<id>`
- `/faculty/cycles/<id>/activate`
- `/faculty/cycles/<id>/close`
- `/faculty/cycles/<id>/delete`
- `/faculty/reports/<id>`
- `/faculty/reports/<id>/verify`
- `/faculty/reports/<id>/reject`
- `/faculty/reports/<id>/download`

### Floor-side report routes
- `/reports`
- `/reports/<id>/download`

### Suggestion/feedback merge
- `/feedbacks` is now the combined page for:
  - meal evaluations
  - suggestions
- `/suggestions` still exists for compatibility, but GET now redirects to `/feedbacks#suggestions`

See also:
- `ROUTE_MAP.md`

---

## 5. Auth and Session Behavior

### Faculty-specific auth
Faculty routes use Faculty-specific session protection.

Implemented behavior:
- Faculty timeout redirects to Faculty login with a flash banner.
- Faculty logout redirects to Faculty login.
- Faculty-only pages are protected by Faculty guards.

Main code:
- `app.py`
- `blueprints/faculty/routes.py`
- `blueprints/auth/routes.py`

### Important exception
`/reports` and `/reports/<id>/download` live inside the Faculty blueprint but are not Faculty-only.

Why this matters:
- A broad Faculty guard originally redirected Pantry Heads/Admins to Faculty login when they opened Reports.
- This was fixed by exempting:
  - `faculty.reports_page`
  - `faculty.download_floor_submission`

If this breaks again, check:
- `app.py`
- `blueprints/faculty/routes.py`

---

## 6. File Storage Memory

### Current server-side storage design
Faculty-uploaded PDFs are stored on the Oracle VM filesystem, outside the Git working tree.

Configured root:
- `REPORT_STORAGE_ROOT`

Current production target:
- `/home/ubuntu/ajs-pantry-data/reports`

App default if env is missing:
- `~/ajs-pantry-data/reports`

Main code:
- `app.py`
- `blueprints/faculty/routes.py`

### Important storage caveat
`FacultyReportSubmission.storage_path` currently stores an absolute filesystem path.

Implication:
- If someone uploads through a locally running app that points to the production DB, the DB can end up storing a Windows path like `C:\...`
- Production then cannot find that file.

Operational rule:
- Upload Faculty PDFs only through the deployed Oracle-hosted app
- Do not upload from a local dev app against production DB

### Server checks used during debugging
- Confirm configured root:
  - `dotenv -f .env run -- python - <<'PY' ...`
- Search PDFs on server:
  - `find /home/ubuntu -type f -name "*.pdf"`
- Inspect submission paths:
  - query `FacultyReportSubmission.storage_path`

Potential future hardening:
- Store relative paths in DB instead of absolute paths

---

## 7. Cycle Delete Safety

Faculty can delete a cycle.

Delete behavior currently includes:
- delete linked `Budget` rows for that cycle
- delete linked `FacultyReportSubmission` rows
- clear linked `Bill.report_submission_id`
- delete saved `ExpensePrintReport` rows for the cycle
- delete stored PDFs from disk

Main code:
- `blueprints/faculty/routes.py`
- helper: `_delete_cycle_related_data`

---

## 8. Expenses Page Memory

### Why old budgets still appear
The Expenses page shows all visible `Budget` rows for the floor, not just Faculty cycle budgets.

Visibility rule:
- all budgets where `cycle_id IS NULL`
- plus budgets from non-draft Faculty cycles

Main code:
- `blueprints/utils.py`
  - `visible_budget_condition()`
- `blueprints/finance/routes.py`

This is why older PH-era allocations can still appear on Expenses even if they are not part of the newer Faculty cycle system.

---

## 9. Feedbacks Page Merge

The old separate `Suggestions` and `Feedbacks` UI was merged into one combined `Feedbacks` page.

Important architecture note:
- UI is merged
- data models are not merged

Why:
- `Suggestion` still supports voting and dish-linked idea capture
- `Feedback` still drives ratings, performance metrics, and analytics

Current behavior:
- main tab is `Feedbacks`
- combined template is `templates/feedbacks.html`
- `/suggestions` GET redirects into the combined page
- vote/delete suggestion endpoints remain unchanged

Main code:
- `blueprints/pantry/routes.py`
- `templates/feedbacks.html`
- `templates/base.html`
- `templates/dashboard.html`

---

## 10. Faculty Mobile Responsiveness

Faculty portal was later reworked for mobile.

Main UX improvements:
- mobile top bar added
- off-canvas sidebar navigation
- card/table layouts become stacked mobile rows
- action buttons become full-width on small screens
- cycle detail and report detail are readable on phones

Important bug already fixed:
- mobile menu opened but links were not tappable
- cause was sidebar stacking layer versus backdrop
- fixed by raising Faculty sidebar z-index

Main code:
- `templates/faculty/base.html`
- `templates/faculty/dashboard.html`
- `templates/faculty/cycles.html`
- `templates/faculty/cycle_detail.html`
- `templates/faculty/report_detail.html`
- `templates/faculty/profile.html`

---

## 11. Key Files to Check First Next Time

If debugging Faculty:
- `models.py`
- `app.py`
- `blueprints/faculty/routes.py`
- `blueprints/finance/routes.py`
- `blueprints/auth/routes.py`
- `blueprints/utils.py`
- `templates/reports.html`
- `templates/expenses.html`
- `templates/faculty/base.html`
- `templates/faculty/dashboard.html`
- `templates/faculty/cycles.html`
- `templates/faculty/cycle_detail.html`
- `templates/faculty/report_detail.html`
- `templates/faculty/profile.html`
- `templates/super_admin/tenant_view.html`

If debugging route ownership:
- `ROUTE_MAP.md`

If debugging deployment/storage:
- `/etc/systemd/system/ajs-pantry.service`
- `/home/ubuntu/ajs-pantry/.env`

---

## 12. Deployment / Verification Checklist

After deploying Faculty-related changes:
- run `flask db upgrade` if models/migrations changed
- restart Gunicorn / systemd service
- verify Faculty login
- verify Faculty logout returns to Faculty login
- verify Faculty timeout redirects cleanly
- verify Pantry Head/Admin can open `/reports`
- verify new PDF uploads land in Oracle storage root
- verify cycle detail and report detail on mobile
- verify `Feedbacks` combined page still handles:
  - suggestion submit
  - suggestion vote
  - feedback submit
  - feedback delete

---

## 13. Future Cleanup Worth Doing

- Move `FacultyReportSubmission.storage_path` to relative-path storage
- Add explicit UI badges for "Legacy budget" vs "Faculty cycle budget" in Expenses
- Consider moving floor-side `/reports` into its own non-Faculty blueprint to reduce auth confusion
- Remove or archive the old standalone `templates/suggestions.html` if it is no longer needed
