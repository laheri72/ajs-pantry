# AJS Pantry — Application Route Map

This file serves as a master index for all routes within the modularized AJS Pantry system. Use this to quickly identify which blueprint and file to modify for any specific URL or functionality.

---

## 1. Auth Blueprint (`blueprints/auth/routes.py`)
*Manages user sessions, security, and profile settings.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/` | `index` | GET | Root redirect (to Login or Dashboard) |
| `/login` | `login` | GET, POST | Member TR number login |
| `/staff-login` | `staff_login` | GET, POST | Admin/Staff specialized login |
| `/change-password` | `change_password` | GET, POST | First-time login password setup |
| `/profile` | `profile` | GET, POST | User profile management |
| `/logout` | `logout` | GET | Session termination |

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
| `/suggestions` | `suggestions` | GET, POST | Community idea board |
| `/suggestions/<id>/vote`| `vote_suggestion` | POST | Upvote/Toggle ideas |
| `/suggestions/<id>/delete`| `delete_suggestion`| POST | Remove an idea |
| `/feedbacks` | `feedbacks` | GET, POST | Meal rating and performance feedback |
| `/feedbacks/<id>/delete` | `delete_feedback` | POST | Remove evaluation |

---

## 3. Finance Blueprint (`blueprints/finance/routes.py`)
*Monetary tracking, budgets, and inter-floor transactions.*

| Route Path | Function Name | Methods | Description |
|:---|:---|:---|:---|
| `/expenses` | `expenses` | GET, POST | Financial ledger and bill recording |
| `/bills/<id>/delete` | `delete_bill` | POST | Remove a bill & revert items to pending |
| `/budgets/add` | `add_budget` | POST | Allocate funds to a floor |
| `/expenses/<id>/delete` | `delete_expense` | POST | Remove legacy expense entry |
| `/lend-borrow` | `lend_borrow` | GET | Inter-floor item lending dashboard |
| `/lend-borrow/create` | `create_lend_borrow` | POST | Log a new lending transaction |
| `/lend-borrow/<id>/mark-returned` | `mark_returned` | POST | Borrower signals item return |
| `/lend-borrow/<id>/verify`| `verify_return` | POST | Lender confirms or rejects return |
| `/expenses/import-receipt` | `import_receipt` | POST | Scan PDF/Image receipts |
| `/expenses/save-imported-bill` | `save_imported_bill`| POST | Persist parsed PDF data to DB |

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

## Helper Functions Reference (`blueprints/utils.py`)
*Critical internal logic used across routes:*
*   `_get_current_user()`: Retrieves User object from session.
*   `_require_user()`: Validates session; redirects to login if missing.
*   `_get_active_floor(user)`: Determines which floor data to display.
*   `_require_staff_for_floor(user)`: RBAC check for privileged ops.
*   `_display_name_for(user)`: Generates consistent UI label for users.
