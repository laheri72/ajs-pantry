# Super Admin Dashboard Enhancements Plan

## 1. Overview
The goal is to transform the Super Admin dashboard from a basic tenant manager into a platform intelligence hub. This will provide the platform owner with actionable insights into financial health, operational efficiency, and user satisfaction across all tenants.

---

## 2. Key Performance Indicators (KPIs) - Top Row Cards
We will expand the current cards to include platform-wide financial and operational metrics.

*   **Global Financial Utilization:** Total spent across all tenants vs. total allocated budget.
    *   *Calculation:* `Sum(actual_cost) / Sum(amount_allocated)`
*   **Operational Completion Rate:** Percentage of daily tasks (Tea, Procurement) completed on time.
    *   *Calculation:* `Completed Tasks / Total Tasks`
*   **Platform Satisfaction Index:** Average rating across all meal feedbacks.
    *   *Calculation:* `Avg(Feedback.rating)`
*   **Active Infrastructure:** Number of active floors across all tenants.

---

## 3. Visual Analytics (Charts)

### A. Platform Growth & Activity (Line/Area Chart)
*   **Data:** Daily count of total interactions (Menus + Tea Tasks + Feedbacks + Procurement) over the last 30 days.
*   **Purpose:** Visualize the "heartbeat" of the platform to identify peak usage periods.

### B. Tenant Performance Matrix (Bubble or Bar Chart)
*   **X-Axis:** Number of Users
*   **Y-Axis:** Average Feedback Rating
*   **Size:** Total Spend
*   **Purpose:** Identify which tenants are high-performing (high rating, efficient spend) vs. those needing support.

### C. Financial Category Breakdown (Donut Chart)
*   **Data:** Aggregated `ProcurementItem` and `Expense` categories (e.g., Grocery, Dairy, Maintenance).
*   **Purpose:** Understand what the platform's resources are being spent on globally.

---

## 4. Operational Insights Sections

### A. "At-Risk" Tenants List
*   **Criteria:** Tenants with low feedback ( < 3.0), high percentage of overdue tea tasks, or 0 activity in the last 7 days.
*   **Action:** Allows Super Admin to proactively reach out to struggling floor admins.

### B. Inter-Tenant Resource Sharing
*   **Data:** Stats from `FloorLendBorrow`.
*   **Metric:** Total items shared this month.
*   **Purpose:** Highlight the community aspect of the platform.

### C. System Health & Audits
*   **Status:** Real-time summary of `PlatformAudit` (e.g., "5 new tenants provisioned this week", "2 password resets").

---

## 5. Implementation Strategy

### Phase 1: Data Aggregation (Backend)
*   Update `super_admin.dashboard` route in `blueprints/super_admin/routes.py` to perform the new SQL aggregations.
*   Optimize queries using SQLAlchemy `func` to ensure performance across many tenants.

### Phase 2: UI Modernization (Frontend)
*   Update `templates/super_admin/dashboard.html`.
*   Introduce `Chart.js` configurations for the new visualizations.
*   Use CSS Grid/Flexbox to create a more "command center" feel.

### Phase 3: Detailed Tenant Views
*   Enhance `tenant_view.html` to mirror some of these stats at a tenant-specific level, allowing the Super Admin to "drill down".
