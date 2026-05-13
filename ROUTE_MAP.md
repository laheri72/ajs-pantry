# AJS Pantry — Application Route Map

This file serves as a master index for all routes within the modularized AJS Pantry system. Use this to quickly identify which blueprint and file to modify for any specific URL or functionality.

---

## 1. Auth Blueprint (`blueprints/auth/routes.py`)
*Manages user sessions, security, and profile settings.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/` | `index` | GET | Root redirect (to Login or Dashboard) |
| `/login` | `login` | GET, POST | Member TR number login; POST is rate-limited by IP and submitted identifier |
| `/staff-login` | `staff_login` | GET, POST | Admin/Staff specialized login; POST is rate-limited by IP and submitted identifier/role |
| `/change-password` | `change_password` | GET, POST | First-time login password setup |
| `/profile` | `profile` | GET, POST | User profile management |
| `/logout` | `logout` | GET | Session termination |

---

## 1A. Faculty Blueprint (`blueprints/faculty/routes.py`)
*Faculty tenant-wide office: budget cycles, report review, member management/imports, meal insights, and floor submissions.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/faculty/login` | `login` | GET, POST | Faculty portal login; POST is rate-limited by IP and submitted identifier |
| `/faculty/dashboard` | `dashboard` | GET | Cached Faculty overview for active users, roles, planned menus, and active cycle status |
| `/faculty/members` | `members` | GET | Faculty member directory with search, floor, role filters, role actions, and Excel import modal |
| `/faculty/members/<id>/role` | `update_member_role` | POST | Assign/demote `member`, `pantryHead`, or `teaManager` for active Faculty-visible users |
| `/faculty/members/<id>/deactivate` | `deactivate_member` | POST | Soft-deactivate a Faculty-visible user with tenant audit logging |
| `/faculty/import/template` | `import_template` | GET | Download Excel import template (`TR`, `Name`, `Floor`) |
| `/faculty/import/validate` | `validate_import` | POST | Validate uploaded Excel file and return valid/invalid rows as JSON |
| `/faculty/import/commit` | `commit_import` | POST | Bulk-create valid imported members with default password `maskan1447` |
| `/faculty/meal-insights` | `meal_insights` | GET | Planned meal history/upcoming view with feedback ratings and suggestion/vote signals |
| `/faculty/profile` | `profile` | GET, POST | Faculty profile and password management |
| `/faculty/cycles` | `cycles` | GET, POST | Create/list budget cycles with per-floor allocations |
| `/faculty/cycles/<id>` | `cycle_detail` | GET | Floor-wise cycle allocation and submission matrix |
| `/faculty/cycles/<id>/edit` | `edit_cycle` | POST | Update a draft or active cycle and its floor allocations |
| `/faculty/cycles/<id>/activate` | `activate_cycle` | POST | Activate a draft cycle |
| `/faculty/cycles/<id>/close` | `close_cycle` | POST | Close an active cycle |
| `/faculty/cycles/<id>/delete` | `delete_cycle` | POST | Delete a cycle and all linked budgets/submissions/PDFs |
| `/faculty/reports/<id>` | `report_detail` | GET | Faculty review page for one floor submission |
| `/faculty/reports/<id>/verify` | `verify_report` | POST | Approve a submitted report |
| `/faculty/reports/<id>/reject` | `reject_report` | POST | Reject a submitted report with notes |
| `/faculty/reports/<id>/download` | `download_report` | GET | Download the stored PDF from server storage |
| `/reports` | `reports_page` | GET, POST | Floor-side upload page for Admin/Pantry Head report submissions |
| `/reports/<id>/download` | `download_floor_submission` | GET | Floor-side download of the submitted PDF |
| `/reports/adhoc/<id>/download` | `download_adhoc_report` | GET | Floor-side download of saved ad-hoc expense report PDF |
| `/reports/adhoc/<id>/delete` | `delete_adhoc_report` | POST | Delete floor-side saved ad-hoc expense report PDF |

---

## 2. Pantry Blueprint (`blueprints/pantry/routes.py`)
*Core user-facing features: dashboard, community, and food feedback.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/dashboard` | `dashboard` | GET | Main personalized activity feed |
| `/home` | `home` | GET | Alias redirect to Dashboard |
| `/people` | `people` | GET | Member directory & Performance leaderboards |
| `/calendar` | `calendar` | GET | Monthly view of all floor activities |
| `/special-events` | `create_special_event` | POST | Add events to the calendar |
| `/special-events/<id>/update`| `update_special_event` | POST | Edit a special event |
| `/special-events/<id>/delete`| `delete_special_event` | POST | Remove a special event |
| `/menus` | `menus` | GET, POST | View/Manage daily breakfast plans |
| `/menus/<id>/delete` | `delete_menu` | POST | Remove a menu entry |
| `/suggestions` | `suggestions` | GET, POST | Backward-compatible suggestion endpoint; GET redirects into the combined Feedbacks page |
| `/suggestions/<id>/vote`| `vote_suggestion` | POST | Upvote/Toggle ideas |
| `/suggestions/<id>/delete`| `delete_suggestion`| POST | Remove an idea |
| `/feedbacks` | `feedbacks` | GET, POST | Combined feedback hub for meal evaluations plus suggestions |
| `/feedbacks/<id>/delete` | `delete_feedback` | POST | Remove evaluation |

---

## 3. Finance Blueprint (`blueprints/finance/routes.py`)
*Monetary tracking, budgets, and inter-floor transactions.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/expenses` | `expenses` | GET, POST | Financial ledger and bill recording |
| `/bills/<id>/delete` | `delete_bill` | POST | Remove a bill & revert items to pending |
| `/budgets/add` | `add_budget` | POST | Disabled floor-side budget allocation endpoint (Faculty now owns allocations) |
| `/expenses/<id>/delete` | `delete_expense` | POST | Remove legacy expense entry |
| `/lend-borrow` | `lend_borrow` | GET | Inter-floor item lending dashboard |
| `/lend-borrow/create` | `create_lend_borrow` | POST | Log a new lending transaction |
| `/lend-borrow/<id>/mark-returned` | `mark_returned` | POST | Borrower signals item return |
| `/lend-borrow/<id>/verify`| `verify_return` | POST | Lender confirms or rejects return |
| `/expenses/import-receipt` | `import_receipt` | POST | Scan PDF/Image receipts; rate-limited by tenant/user to protect the OCR worker |
| `/expenses/save-imported-bill` | `save_imported_bill`| POST | Persist parsed PDF data to DB |
| `/expenses/print-reports/save` | `save_print_report` | POST | Persist a saved print-report definition from the Expenses wizard |
| `/bills/<id>/items` | `get_bill_items` | GET | API: Fetch all items for a specific bill (JSON) |


## expense_print_report_bill — write gate (2025-05)
Bill-link rows are only written when faculty_workflow_enabled is True.
Reason: these rows are only consumed by the Faculty submission picker.
For Faculty-off tenants they were dead weight — 1,652 rows were cleaned up
before the gate was added. Do not remove the gate without re-evaluating
the Faculty submission flow in blueprints/faculty/routes.py.

---

## 4. Ops Blueprint (`blueprints/ops/routes.py`)
*Daily pantry operations: tea duties, procurement, and requests.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/tea` | `tea` | GET, POST | Tea duty scheduling & tracking |
| `/tea/complete/<id>` | `complete_tea_task` | POST | Mark tea duty as done |
| `/requests` | `requests` | GET, POST | Personal/Floor service requests |
| `/requests/<id>/status` | `update_request_status`| POST | Approve or reject requests |
| `/requests/<id>/delete` | `delete_request` | POST | Cancel a request |
| `/procurement` | `procurement` | GET, POST | Shopping list management |
| `/procurement/complete/<id>`| `complete_procurement_item`| POST | Mark item as bought |
| `/procurement/revoke/<id>` | `revoke_procurement_item` | POST | Revert bought item to pending |
| `/procurement/delete/<id>` | `delete_procurement_item` | POST | Remove item from list |
| `/procurement/suggest` | `procurement_suggest`| GET | Autocomplete for item names |
| `/procurement/suggest-qty` | `procurement_suggest_qty`| GET | Intelligent quantity suggestions |

---

## 5. Admin Blueprint (`blueprints/admin/routes.py`)
*System-wide management and privileged controls.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/admin/active-floor` | `set_active_floor` | POST | Switch Admin view to specific floor |
| `/admin` | `admin` | GET, POST | Super-admin dashboard & User creation |
| `/admin/floor-members` | `admin_floor_members` | GET | API: Fetch members for a floor |
| `/floor-admin` | `floor_admin` | GET, POST | Pantry Head controls & Penalty (Garamat) |
| `/teams` | `create_team` | POST | Create floor-specific team |
| `/teams/<id>/update` | `update_team` | POST | Edit team icon/name |
| `/teams/<id>/delete` | `delete_team` | POST | Remove team |
| `/teams/<id>/members/add`| `add_team_member` | POST | Add user to team |
| `/teams/<id>/members/remove`| `remove_team_member`| POST | Remove user from team |

---

## 6. Main Blueprint (`blueprints/main/routes.py`)
*System assets and offline support.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/service-worker.js` | `service_worker` | GET | PWA service worker file |
| `/manifest.json` | `manifest` | GET | PWA manifest file |
| `/offline` | `offline` | GET | Fallback page for no connectivity |

---

## 7. Super Admin Blueprint (`blueprints/super_admin/routes.py`)
*Platform-wide tenant and global catalog governance.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/platform-admin/login` | `login` | GET, POST | Super Admin login; POST is rate-limited by IP and submitted username |
| `/platform-admin/dashboard` | `dashboard` | GET | Platform analytics dashboard |
| `/platform-admin/tenants` | `tenants_list` | GET | Tenant list and infrastructure status |
| `/platform-admin/tenants/<tenant_id>` | `tenant_detail` | GET | Tenant configuration and Faculty account management |
| `/platform-admin/dishes` | `global_dishes` | GET | Global dish catalog, duplicate candidates, trends, and audit log |
| `/platform-admin/dishes/add` | `add_global_dish` | POST | Create a global dish |
| `/platform-admin/dishes/<id>/edit` | `edit_global_dish` | POST | Edit global dish name/category |
| `/platform-admin/dishes/<id>/archive` | `archive_global_dish` | POST | Archive or restore a global dish |
| `/platform-admin/dishes/<id>/estimate` | `update_dish_estimate` | POST | Create or update the 30-person dish estimate |
| `/platform-admin/dishes/merge/preview` | `preview_dish_merge` | POST | Preview a manual duplicate merge |
| `/platform-admin/dishes/merge/confirm` | `confirm_dish_merge` | POST | Confirm manual merge and archive duplicate dishes |

---

## Helper Functions Reference (`blueprints/utils.py`)
*Critical internal logic used across routes:*
*   `_get_current_user()`: Retrieves User object from session.
*   `_require_user()`: Validates session; redirects to login if missing.
*   `_get_active_floor(user)`: Determines which floor data to display.
*   `_require_staff_for_floor(user)`: RBAC check for privileged ops.
*   `_display_name_for(user)`: Generates consistent UI label for users.
*   `faculty_visible_users_query()`: Canonical Faculty-visible user scope; excludes admin/super_admin and inactive users.
*   `log_tenant_audit()`: Adds `TenantAuditLog` rows for tenant-scoped administrative mutations.
