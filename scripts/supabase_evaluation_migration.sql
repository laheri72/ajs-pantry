-- Dish + menu-tagged evaluations (Postgres / Supabase)
-- Safe to run multiple times.

-- 1) Constant dish catalog
CREATE TABLE IF NOT EXISTS dish (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    created_by_id INTEGER REFERENCES "user"(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Case-insensitive uniqueness for dish names
CREATE UNIQUE INDEX IF NOT EXISTS uq_dish_name_lower ON dish (LOWER(name));

-- 2) Menus reference a dish (keeps menu.title for backwards compatibility / display)
ALTER TABLE menu
    ADD COLUMN IF NOT EXISTS dish_id INTEGER REFERENCES dish(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_menu_dish_id ON menu (dish_id);

-- Optional backfill: create dishes from existing menu titles, then link menus.
-- Uncomment if you want historical menus to map to dishes automatically.
INSERT INTO dish (name)
SELECT DISTINCT title
FROM menu
WHERE title IS NOT NULL AND BTRIM(title) <> ''
ON CONFLICT DO NOTHING;

UPDATE menu
SET dish_id = d.id
FROM dish d
WHERE menu.dish_id IS NULL
  AND menu.title IS NOT NULL
  AND LOWER(d.name) = LOWER(menu.title);

-- 3) Feedbacks become evaluations by tagging a menu
ALTER TABLE feedback
    ADD COLUMN IF NOT EXISTS menu_id INTEGER REFERENCES menu(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_feedback_menu_id ON feedback (menu_id);

-- -- Optional: one evaluation per user per menu (prevents spam and stabilizes leaderboards)
-- CREATE UNIQUE INDEX IF NOT EXISTS uq_feedback_menu_user
--     ON feedback (menu_id, user_id)
--     WHERE menu_id IS NOT NULL;

-- Optional: updated timestamp for edits/upserts
ALTER TABLE feedback
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

