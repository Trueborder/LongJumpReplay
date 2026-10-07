-- Allow a failed webhook attempt to be retried without duplicating completed work.
ALTER TABLE stripe_events ADD COLUMN processing_status TEXT NOT NULL DEFAULT 'processed' CHECK(processing_status IN ('processing','processed','failed'));
ALTER TABLE stripe_events ADD COLUMN last_error TEXT;
