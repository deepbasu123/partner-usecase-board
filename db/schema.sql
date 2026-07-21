-- Partner Use-Case Board - Lakebase (Postgres) schema
-- Three tables: partners, use_cases, responses.
-- Applied to an existing Lakebase instance on the target workspace.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- for gen_random_uuid()

CREATE TABLE IF NOT EXISTS partners (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email        text NOT NULL UNIQUE,
    company      text NOT NULL,
    contact_name text,
    clerk_user_id text UNIQUE,
    verified     boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS use_cases (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title       text NOT NULL,
    description text NOT NULL,
    industry    text,
    region      text,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    posted_by   text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    closed_at   timestamptz
);

CREATE TABLE IF NOT EXISTS responses (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    use_case_id  uuid NOT NULL REFERENCES use_cases(id) ON DELETE CASCADE,
    partner_id   uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    approach     text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (use_case_id, partner_id)   -- one expression of interest per partner per case
);

CREATE INDEX IF NOT EXISTS idx_use_cases_status ON use_cases(status);
CREATE INDEX IF NOT EXISTS idx_responses_use_case ON responses(use_case_id);
