-- AJS Pantry: Multi-Tenant Stealth Migration
-- Run this in Supabase SQL Editor

-- 1. Create Tenants Table
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    subscription_status TEXT DEFAULT 'active'
);

-- 2. Create Default Tenant
INSERT INTO tenants (name, is_active, subscription_status) 
VALUES ('Default Tenant', true, 'active')
ON CONFLICT DO NOTHING;

-- 3. Add tenant_id to all operational tables
DO $$ 
DECLARE 
    t_id UUID;
    tbl TEXT;
    -- List of all tables from models.py that need isolation
    tables TEXT[] := ARRAY[
        'user', 'dish', 'menu', 'expense', 'tea_task', 
        'suggestion', 'suggestion_vote', 'feedback', 
        'request', 'bill', 'procurement_item', 'team', 
        'team_member', 'budget', 'floor_lend_borrow', 
        'special_event', 'announcement', 'garamat'
    ];
BEGIN
    SELECT id INTO t_id FROM tenants WHERE name = 'Default Tenant' LIMIT 1;

    FOREACH tbl IN ARRAY tables LOOP
        -- Add column if not exists
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = tbl AND column_name = 'tenant_id'
        ) THEN
            EXECUTE format('ALTER TABLE %I ADD COLUMN tenant_id UUID REFERENCES tenants(id)', tbl);
            
            -- Update existing rows to default tenant
            EXECUTE format('UPDATE %I SET tenant_id = %L WHERE tenant_id IS NULL', tbl, t_id);
            
            -- Add index for performance
            EXECUTE format('CREATE INDEX idx_%I_tenant_id ON %I(tenant_id)', tbl, tbl);
            
            -- Make it nullable for Super Admin flexibility, but required for operational data via logic
            -- Optional: EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id SET NOT NULL', tbl);
        END IF;
    END LOOP;
END $$;

-- 4. Promote current Administrator to Super Admin (Platform Level)
-- Super Admins have tenant_id = NULL
UPDATE "user" SET tenant_id = NULL, role = 'super_admin' WHERE username = 'Administrator';
