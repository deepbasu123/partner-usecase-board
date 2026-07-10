# Partner Use-Case Board — Design Spec

**Date:** 2026-07-10
**Author:** Deep Basu (Databricks Solutions Architect)
**Status:** Approved design, pending implementation plan

## Problem

Beth was looking for a Workforce Management solution in the ANZ channel. We tried to
crowd-source it through the partner ecosystem (via Allyson) and got no response. We want a
lightweight way for Databricks to **post use cases we need partner help on**, and for
**GT partners to see them and raise their hand**. Start super simple, invite a controlled
set of GT partners, see how it goes, iterate later.

## Goal

A pilot with one loop that works end to end:

> Databricks posts a use case → registered partners are notified and can browse it →
> a partner submits a structured expression of interest → Databricks is notified and can
> compare responses.

## Hard platform constraint (verified against official docs)

**Databricks Apps cannot be public.** Official docs:
> "You can't make Databricks apps public. Anonymous access and bypassing single sign-on
> (SSO) are not supported."
> — https://docs.databricks.com/en/dev-tools/databricks-apps/permissions.html

Verified points (double-checked on a second model):
- Every end user of a Databricks App must authenticate via workspace SSO and hold `CAN_USE`.
- Embedding an app in an external site still requires the viewer to be an authenticated
  Databricks user (https://docs.databricks.com/en/dev-tools/databricks-apps/embed.html).
- The only "external collaborator" path is SCIM/JIT identity federation — admin-driven,
  not self-serve email signup.

**Consequence:** the partner-facing surface CANNOT be a Databricks App. It must be hosted
outside Databricks Apps. Lakebase, however, **can** be reached from an external application
(Postgres drivers / OAuth token / password), per
https://docs.databricks.com/aws/en/oltp/projects/connect — so the external portal can use
Databricks data as its single source of truth.

> Verification caveat: the Lakebase Data API (PostgREST-style) doc page 404'd at design
> time, so its public-reachability/auth model is unconfirmed. The design therefore uses the
> **doc-confirmed Postgres-driver-from-a-backend** path, not direct SPA→Lakebase calls.

## Architecture — two surfaces, one database

```
   PARTNERS (no Databricks account)          DATABRICKS (Deep, Beth, Allyson)
            │                                          │
            ▼                                          ▼
  ┌──────────────────────┐              ┌──────────────────────────┐
  │  PUBLIC PARTNER PORTAL│              │   ADMIN COCKPIT           │
  │  React SPA + FastAPI  │              │   Databricks App          │
  │  on GCP Cloud Run     │              │   (behind workspace SSO)  │
  │                       │              │                           │
  │ • Sign up w/ email    │              │ • Post/edit/close cases   │
  │ • Browse live board   │              │ • See all EOIs per case   │
  │ • Submit EOI on a case│              │ • See registered partners │
  └──────────┬───────────┘              └────────────┬──────────────┘
             │        both read/write                │
             └───────────────┬───────────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │  LAKEBASE (Postgres)  │  ← single source of truth
                  │  partners │ use_cases │
                  │  responses            │
                  └──────────┬───────────┘
                             │ triggers
                             ▼
                    ┌─────────────────┐
                    │  EMAIL (notify) │
                    │ • partner signup│
                    │ • new use case  │
                    │ • new EOI → DBX │
                    └─────────────────┘
```

- **Partner portal** — React SPA + FastAPI backend on **GCP Cloud Run** (public HTTPS,
  scales to zero, GCP sandbox access available). SPA never touches Lakebase directly; it
  only calls its own FastAPI, which holds the DB credentials server-side.
- **Admin cockpit** — a Databricks App (behind workspace SSO) deployed to **deep-test**.
  Only Databricks employees can reach it.
- **Lakebase** — single Postgres source of truth for both surfaces. No syncing.
- **Email** — fires on the three lifecycle events below.

## Data model (Lakebase / Postgres) — three tables

### `partners`
| column | type | notes |
|---|---|---|
| `id` | uuid (pk) | |
| `email` | text, unique | sign-up identity |
| `company` | text | GT partner firm name |
| `contact_name` | text | optional |
| `created_at` | timestamptz | default now() |
| `verified` | boolean | for later email verification; default true in pilot |

### `use_cases`
| column | type | notes |
|---|---|---|
| `id` | uuid (pk) | |
| `title` | text | e.g. "Workforce Management — ANZ" |
| `description` | text | the ask, in Databricks' words |
| `industry` | text | optional tag |
| `region` | text | optional tag |
| `status` | text | `open` / `closed` |
| `posted_by` | text | Databricks admin email (from SSO) |
| `created_at` | timestamptz | default now() |
| `closed_at` | timestamptz | nullable |

### `responses` (structured expression of interest)
| column | type | notes |
|---|---|---|
| `id` | uuid (pk) | |
| `use_case_id` | uuid (fk → use_cases) | |
| `partner_id` | uuid (fk → partners) | |
| `approach` | text | how the partner would tackle it / relevant experience |
| `created_at` | timestamptz | default now() |
| unique (`use_case_id`, `partner_id`) | | one EOI per partner per case |

Responses are **private to Databricks** — no partner-to-partner visibility (partners can't
tip off competitors).

## Authentication

- **Partner portal (public):** lightweight, **no password**. Partner enters email +
  company; backend creates/looks up the `partners` row and sets a signed session cookie so
  the board recognizes them on return. No password storage, no OTP in the pilot. Email-link
  verification is a later add (the `verified` column exists for it).
- **Admin cockpit:** real Databricks workspace SSO (it is a Databricks App). Only Databricks
  employees can reach it; `posted_by` is taken from the authenticated identity.

## Email notifications — three triggers

1. **Partner signs up** → welcome/confirmation email to the partner.
2. **Databricks posts a use case** → email to **all** registered partners with title, the
   ask, and a link to the board.
3. **Partner submits an EOI** → email to the case's `posted_by`, plus an optional
   configurable shared address (e.g. you + Beth + Allyson), with the partner's company and
   their approach.

Sending mechanism to be confirmed early in implementation (candidates: Gmail API via the
`/gmail` skill for pilot volume, or a transactional email API). Not locked until verified to
send cleanly from Cloud Run under the environment's supply-chain lockdown.

## Repo layout

```
partner-usecase-board/
├── portal-frontend/     React SPA (partner board + signup + EOI form)
├── portal-backend/      FastAPI: public API, Lakebase access, email, sessions → Cloud Run
├── admin-app/           Databricks App (FastAPI + React): post/manage cases, view EOIs → deep-test
├── db/                  Lakebase schema + seed (the 3 tables)
└── deploy/              Cloud Run + Databricks Apps deploy scripts
```

## Testing / verification

Nothing is reported as "done" until exercised end to end and independently checked by a
verification agent (different model), per working standards.

- **DB:** schema applies cleanly; FKs and the `(use_case_id, partner_id)` unique constraint hold.
- **Portal:** sign up → `partners` row + welcome email; browse open cases; submit EOI →
  `responses` row + notification email; duplicate EOI blocked by the unique constraint.
- **Admin:** SSO gate blocks non-Databricks users; post case → partners emailed; EOIs
  visible joined to partner details.
- **Full loop, live, once:** post in admin → partner sees it on the board → partner responds
  → Databricks sees the EOI. Verified against docs and the running system before sign-off.

## Explicitly OUT of the pilot (YAGNI)

- Partner passwords / OTP / email-link verification (`verified` column reserved for later)
- Partner-to-partner visibility (EOIs stay private to Databricks)
- GT-partner gating / allowlist (anyone with the link can sign up in the pilot)
- Matching/scoring, file uploads, in-app messaging, analytics dashboard

## Known risks

- **Public signup, ungated.** During the pilot anyone with the link can sign up — the portal
  is genuinely public and not restricted to a vetted GT-partner list. Acceptable for a
  controlled invite; not a locked allowlist yet.
- **NPM lockdown.** The React build needs npm; the environment has an NPM/PyPI lockdown.
  Workable via internal proxy + pinned deps, but must be verified early, not assumed.
- **Email from Cloud Run.** Sending path must be verified to work under the lockdown before
  it's relied on.
- **Lakebase Data API unconfirmed.** Design avoids it deliberately; if we later want
  direct SPA→Lakebase, its public/auth model must be verified first.
