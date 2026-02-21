-- Bill Numbering + Systematic Expenses Migration
-- Safe to run multiple times.

-- 1) Bill table to group procurement items
CREATE TABLE IF NOT EXISTS bill (
    id SERIAL PRIMARY KEY,
    bill_no VARCHAR(100) NOT NULL,
    bill_date DATE NOT NULL,
    shop_name VARCHAR(100),
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    floor INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2) Update ProcurementItem to link to Bill
ALTER TABLE procurement_item
    ADD COLUMN IF NOT EXISTS bill_id INTEGER REFERENCES bill(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_procurement_item_bill_id ON procurement_item (bill_id);