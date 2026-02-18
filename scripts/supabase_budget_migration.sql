-- Budget + Procurement-Linked Expenses Migration
-- Safe to run multiple times.

-- 1) Budget allocation table
CREATE TABLE IF NOT EXISTS budget (
    id SERIAL PRIMARY KEY,
    floor INTEGER NOT NULL,
    amount_allocated NUMERIC(12, 2) NOT NULL DEFAULT 0,
    allocation_type VARCHAR(20) NOT NULL, -- weekly, monthly, 15days, manual
    start_date DATE NOT NULL,
    end_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_budget_floor ON budget (floor);

-- 2) Update ProcurementItem to track costs
ALTER TABLE procurement_item
    ADD COLUMN IF NOT EXISTS actual_cost NUMERIC(12, 2) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS expense_recorded_at TIMESTAMPTZ DEFAULT NULL;

-- 3) Optional: Backfill logic for legacy expenses (Inquiry only for now)
-- We keep the 'expense' table for history, but new costs go into procurement_item.
-- If a procurement item was manually recorded in 'expense' table previously, 
-- they remain separate unless manually reconciled by the user.
