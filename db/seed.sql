-- One sample open use case so the board isn't empty on first load.
-- No PII: posted_by is a placeholder address.

INSERT INTO use_cases (title, description, industry, region, status, posted_by)
VALUES (
  'Workforce Management solution — ANZ',
  'Seeking a partner with a proven Workforce Management solution deployable on Databricks for an ANZ customer. Looking for accelerators, prior implementations, and a delivery team who can move quickly.',
  'Cross-industry', 'ANZ', 'open', 'admin@example.com'
)
ON CONFLICT DO NOTHING;
