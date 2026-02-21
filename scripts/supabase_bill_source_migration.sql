-- Add tracking columns for PDF imports
ALTER TABLE bill 
ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'manual',
ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255);

-- Index for source filtering if needed later
CREATE INDEX IF NOT EXISTS ix_bill_source ON bill (source);
