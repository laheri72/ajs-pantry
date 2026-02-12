-- Teams + menu team assignment (Postgres / Supabase)
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS team (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    icon VARCHAR(50),
    floor INTEGER NOT NULL,
    created_by_id INTEGER REFERENCES "user"(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_team_floor_name ON team (floor, name);
CREATE INDEX IF NOT EXISTS ix_team_floor ON team (floor);

CREATE TABLE IF NOT EXISTS team_member (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_team_member_team_user ON team_member (team_id, user_id);
CREATE INDEX IF NOT EXISTS ix_team_member_user_id ON team_member (user_id);

ALTER TABLE menu
    ADD COLUMN IF NOT EXISTS assigned_team_id INTEGER REFERENCES team(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_menu_assigned_team_id ON menu (assigned_team_id);
