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

### 3.4 Room Champions (Manual Linking) Feature
*   **Purpose:** Allows pantry heads to manually designate specific Rooms (Teams) as "Champions" for any dish in the global catalog, bypassing waiting for user feedback ratings.
*   **Model:** `DishChampion` stores many-to-many associations between `Team` and `Dish` with a unique constraint on `(tenant_id, team_id, dish_id)`.
*   **Endpoints:**
    1.  `GET /menus/team-champions/<team_id>`: Returns manually linked champion dishes for a Room.
    2.  `POST /menus/team-champions/set`: Atomically clears any existing champion room for a dish on the active floor and links the new room (or unlinks if the parameter is empty).
    3.  `GET /menus/champions-directory`: Returns the full mapping of dishes to champion teams for the current floor.
*   **UX Flow:**
    *   Room selection is at the top of the "Schedule Meal" modal. Selecting a room loads its champion dishes as clickable tags.
    *   Selecting a main dish (via shortcut tag or dropdown) hides the champion tag panel and reveals the rating-based "Dish Insights" panel. A "Show Champions" button lets users reopen the panel.
    *   "Manage Champions" modal houses a dual-accordion dashboard (Assigned vs Unassigned) with inline dropdown selection, instant auto-saving status animations, and an active search filter that automatically expands accordions when matches are found.


### 3.5 Room Rotation (Planning Engine) Feature
*   **Purpose**: Allows Pantry Heads to define a structured cooking turn rotation for rooms (teams) on their floor. Pauses/resumes automatically for holidays/leaves without losing any room's turn.
*   **Models**: 
    1.  `RoomRotationSettings`: Stores rotation start date, waari count (consecutive turn duration), and weekly active days mask.
    2.  `RoomRotationOrder`: Maintains the user-sorted sequence of rooms.
    3.  `RoomRotationException`: Stores leave/skip days (holiday) and manual overrides.
*   **Endpoints**:
    1.  `GET /menus/rotation/settings`: Returns active rotation rules and sorted sequence of rooms.
    2.  `POST /menus/rotation/save`: Saves active rotation sequence, start date, waari duration, and active weekdays.
    3.  `POST /menus/rotation/exceptions/add`: Registers a leave/skip exception.
    4.  `POST /menus/rotation/exceptions/remove`: Removes an exception.
    5.  `GET /menus/rotation/slated-team?date=YYYY-MM-DD`: Returns the slated team ID and status for a given calendar date.
*   **UX Flow & Integration**:
    *   **Planner Modal Wizard**: Houses steps for sorting rooms (using HTML5 drag-and-drop handles and accessibility Up/Down buttons), defining benchmark parameters, and adding/removing leave dates.
    *   **Dynamic Slated Badges**: If a calendar day has no scheduled menus, a dashed, interactive slated chip (e.g. `Slated: Room 2091`) is displayed. Clicking it opens the Schedule Modal pre-populated with that date and team.
    *   **Auto-populate Selection**: When the Schedule modal opens or its date input changes, the slated team for that date is automatically fetched and selected. This in turn triggers loading the team's custom champion dishes.

### 3.6 Multi-Theme & UI/UX Navigation Customization
*   **Purpose:** Allows members and pantry heads to customize their dashboard aura across 4 distinct color schemes plus the original dark mode:
    1.  `Teal Green` (Default)
    2.  `Navy Blue` (Ocean branding using a custom ship steering wheel SVG helm icon in the dropdown and dynamic circular selector badge).
    3.  `Platinum Elegance` (Light, airy slate/silver expensive styling).
    4.  `Imperial Saffron & Gold` (Traditional richness with saffron orange and metallic gold accents).
    5.  `Dark Mode` (Kept fully intact and selectable inside the dropdown).
*   **Persistency:** Theme preference is stored in `localStorage` under `selected-theme` (with fallback sync to `theme` for backward compatibility).
*   **FOUC Bootloader:** A self-contained inline script block immediately follows the opening `<body>` tag in [base.html](file:///D:/My%20Sites/ajs-pantry/templates/base.html) to apply the active theme class to `<body>` prior to layout painting, avoiding page flash.
*   **Calendar UX Enhancements:** 
    1.  *Today Indicator:* Restyled to use an Indigo theme (solid circular date badge and background tint) to distinguish it from the teal cooking turn reminder cards.
    2.  *Dynamic Card Hover:* Calendar day cards elevate (`translateY(-3px)`) and expand slightly on hover, applying a drop shadow and border highlights matching the selected theme.
    3.  *Exclusion validation:* Form inputs for dish selection automatically toggle state to prevent duplicate inputs (manual text fields are disabled if a dropdown selection exists, and the dropdown is cleared if manual typing starts).

### 3.7 Bulk Week Planner Refactor
*   **Purpose:** Compact grid scheduler supporting week-shifting navigation, locked/disabled past or pre-scheduled dates, automatic pre-population of slated rooms with leaf/holiday exceptions and user-absence alerts, champion dish quick-fill chips, and inline menu estimate modal stacking.
*   **Spam-Safe Notification:** 
    1.  *Consolidated Client Scan:* Gathers unique assigned rooms, allowing selection of at most 3 recipients per room via checkbox limits.
    2.  *Silent Option:* "Create Without Informing (Silent)" submits empty recipient lists, bypassing email dispatch completely.
    3.  *Consolidated Backend Route:* Compiles a single recipient map sending exactly one email per person listing all weekly turns (bypassing Google spam limits).
*   **Date Generation:** Uses `formatDateLocal()` instead of UTC `.toISOString()` to prevent day-shifting bugs in local timezones.

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
