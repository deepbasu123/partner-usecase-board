-- Link Clerk identities to partner profiles. Nullable so existing rows are
-- valid; stamped on first Clerk sign-in (linked by email).
ALTER TABLE partners ADD COLUMN IF NOT EXISTS clerk_user_id text UNIQUE;
