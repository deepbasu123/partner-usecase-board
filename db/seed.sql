-- One sample open use case so the board isn't empty on first load.
-- No PII: posted_by is a placeholder address.

-- Idempotent: use_cases has only a UUID PK, so ON CONFLICT can't dedupe by
-- title. Guard on the title instead so re-running provisioning is safe.
INSERT INTO use_cases (title, description, industry, region, status, posted_by)
SELECT
  'Workforce Management solution - ANZ',
  'Seeking a partner with a proven Workforce Management solution deployable on Databricks for an ANZ customer. Looking for accelerators, prior implementations, and a delivery team who can move quickly.',
  'Cross-industry', 'ANZ', 'open', 'admin@example.com'
WHERE NOT EXISTS (
  SELECT 1 FROM use_cases WHERE title = 'Workforce Management solution - ANZ'
);
