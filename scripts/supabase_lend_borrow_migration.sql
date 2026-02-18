-- Inter-Floor Lend & Borrow Migration
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS floor_lend_borrow (
    id SERIAL PRIMARY KEY,
    lender_floor INTEGER NOT NULL,
    borrower_floor INTEGER NOT NULL,
    item_name VARCHAR(120) NOT NULL,
    quantity VARCHAR(50) NOT NULL,
    item_type VARCHAR(20) NOT NULL DEFAULT 'grocery', -- grocery, equipment, money, other
    notes TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, returned, completed, cancelled
    created_by_id INTEGER REFERENCES "user"(id) ON DELETE SET NULL,
    borrower_marked_at TIMESTAMPTZ,
    lender_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_lend_borrow_lender ON floor_lend_borrow (lender_floor);
CREATE INDEX IF NOT EXISTS ix_lend_borrow_borrower ON floor_lend_borrow (borrower_floor);
CREATE INDEX IF NOT EXISTS ix_lend_borrow_status ON floor_lend_borrow (status);
