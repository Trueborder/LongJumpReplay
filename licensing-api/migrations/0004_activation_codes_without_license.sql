-- Let the desktop app verify an email before a licence exists without making
-- that code usable as a customer-portal login. Existing rows are portal codes.
ALTER TABLE portal_login_codes
  ADD COLUMN purpose TEXT NOT NULL DEFAULT 'portal'
  CHECK (purpose IN ('portal', 'activation'));

CREATE INDEX idx_portal_codes_purpose_email_open
  ON portal_login_codes (purpose, email, used_at, created_at);
