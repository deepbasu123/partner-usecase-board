# Resend Notification Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the board's three notification emails (welcome / new-use-case / new-EOI) to actually send through Resend, replacing the `NotImplementedError` stub in `board_api/email.py`.

**Architecture:** `board_api/email.py::_send()` becomes a real HTTPS POST to Resend's REST API (`https://api.resend.com/emails`). No new backend dependency — use Python stdlib `urllib.request` (adding the `resend` SDK is avoided because of the PyPI lockdown on this machine). The existing `_safe()` best-effort wrapper is kept verbatim, so any Resend failure is logged and swallowed and never breaks the HTTP request that triggered it. The three `send_*` functions and all their call sites (signup, admin case-create, EOI submit) are unchanged.

**Tech Stack:** Python 3.13, FastAPI, `urllib.request` (stdlib), pytest + `unittest.mock`, Resend REST API.

## Global Constraints

- **From-address:** always `onboarding@resend.dev` (Resend shared domain). No custom/verified domain — ever. `EMAIL_FROM` env var defaults to this.
- **Deliverability ceiling (known/accepted):** with no verified domain, Resend only reliably delivers to the **Resend account-owner address**. External partner mail won't deliver until a domain is verified (out of scope). Do not add code that implies broader delivery.
- **No new pip dependency:** use `urllib.request` from the stdlib. Do not add `resend`, `httpx`, or `requests` to `requirements.txt`.
- **Best-effort invariant:** `_safe()` must keep swallowing all exceptions from `_send()` — a mail failure can never turn a 200/201 signup or EOI into a 500.
- **Secret handling:** the Resend key is read only from the `RESEND_API_KEY` env var, server-side. Never log the key, never ship it to the client, never commit it.
- **No unapproved sends:** the one live end-to-end test send (Task 4) requires showing the user the exact draft and getting explicit approval before sending. Applies even though the recipient is the user's own address.
- **email.py is a canonical copy** (its header says it's copied into other backends). For this Vercel app only `board_api/email.py` is live; edit there.
- **Commit style:** `type(scope): summary` (e.g. `feat(email): ...`), matching git history.
- **Test invocation:** `. .venv/bin/activate && python -m pytest board_api/tests/ -v`. (Note: `run_tests.sh` is stale — it points at the old `portal_backend/` path — do not use it for `board_api`.)

---

### Task 1: Implement `_send()` against Resend via urllib

**Files:**
- Modify: `board_api/email.py:24-29` (the `_send` stub)
- Test: `board_api/tests/test_email.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `_send(to: list[str], subject: str, body: str) -> None` — POSTs to Resend; raises on missing key or non-2xx (so `_safe` logs+swallows). Reads `RESEND_API_KEY` and `EMAIL_FROM` (default `onboarding@resend.dev`) from env at call time.

- [ ] **Step 1: Write the failing tests**

Create `board_api/tests/test_email.py`:

```python
"""Tests for the Resend-backed _send and the best-effort _safe wrapper.

No network: urllib.request.urlopen is patched. These assert the request we
build (URL, auth header, JSON payload) and that _safe swallows failures.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from board_api import email


def _fake_resp(status=200, body=b'{"id":"re_123"}'):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_send_posts_to_resend_with_auth_and_payload(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", "onboarding@resend.dev")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["auth"] = req.get_header("Authorization")
        captured["ctype"] = req.get_header("Content-type")
        captured["body"] = json.loads(req.data.decode())
        return _fake_resp()

    with patch("board_api.email.urllib.request.urlopen", side_effect=fake_urlopen):
        email._send(["me@databricks.com"], "Hi", "Body text")

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer re_test_key"
    assert captured["ctype"] == "application/json"
    assert captured["body"] == {
        "from": "onboarding@resend.dev",
        "to": ["me@databricks.com"],
        "subject": "Hi",
        "text": "Body text",
    }


def test_send_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        email._send(["me@databricks.com"], "Hi", "Body")


def test_send_raises_on_non_2xx(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    with patch("board_api.email.urllib.request.urlopen",
               side_effect=__import__("urllib").error.HTTPError(
                   "https://api.resend.com/emails", 422, "Unprocessable", {}, None)):
        with pytest.raises(Exception):
            email._send(["me@databricks.com"], "Hi", "Body")


def test_safe_swallows_send_failure(monkeypatch):
    """A transport failure must NOT propagate — signup/EOI stay 200/201."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)  # forces _send to raise
    # Must not raise:
    email._safe(["me@databricks.com"], "Hi", "Body")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_email.py -v`
Expected: FAIL — `test_send_posts_to_resend_with_auth_and_payload` errors because `_send` raises `NotImplementedError` (and `email.urllib` doesn't exist yet).

- [ ] **Step 3: Implement `_send` against Resend**

In `board_api/email.py`, add stdlib imports near the top (after the existing `import logging` / `import os`):

```python
import json
import urllib.request
import urllib.error
```

Replace the stub body of `_send` (currently `raise NotImplementedError(...)`) with:

```python
RESEND_ENDPOINT = "https://api.resend.com/emails"


def _send(to: list[str], subject: str, body: str) -> None:
    """Deliver via Resend's REST API using stdlib urllib (no extra dep).

    Raises on missing key or non-2xx so _safe() logs and swallows it. Keep this
    signature stable — send_* and the tests depend on it.
    """
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        raise RuntimeError("RESEND_API_KEY not set")
    payload = json.dumps({
        "from": os.environ.get("EMAIL_FROM", FROM_ADDR),
        "to": to,
        "subject": subject,
        "text": body,
    }).encode()
    req = urllib.request.Request(
        RESEND_ENDPOINT, data=payload, method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if not (200 <= resp.status < 300):
            raise RuntimeError(f"Resend returned {resp.status}")
```

Also change the `FROM_ADDR` default at the top of the file from
`partner-board@example.com` to `onboarding@resend.dev`:

```python
FROM_ADDR = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/test_email.py -v`
Expected: PASS (4 passed). `urllib.error.HTTPError` is a subclass of `Exception`, so the non-2xx test passes; the key-missing tests hit the `RuntimeError` guard; `_safe` swallows.

- [ ] **Step 5: Commit**

```bash
git add board_api/email.py board_api/tests/test_email.py
git commit -m "feat(email): send notifications via Resend REST API (stdlib urllib)"
```

---

### Task 2: Confirm the full suite still passes (regression)

**Files:**
- Test: all of `board_api/tests/`

**Interfaces:**
- Consumes: `_send` from Task 1.
- Produces: nothing; a green gate that Task 1 didn't break signup/EOI, which patch `email.send_welcome` / `email.send_new_eoi` (not `_send`) and so are unaffected.

- [ ] **Step 1: Run the whole backend suite**

Run: `. .venv/bin/activate && python -m pytest board_api/tests/ -v`
Expected: PASS — 27 prior tests + 4 new email tests = 31 passed. (DB-touching tests skip if `DATABASE_URL` is unset; that's expected and not a failure.)

- [ ] **Step 2: Commit (only if any fixup was needed)**

If a test needed adjustment, commit it:

```bash
git add board_api/tests/
git commit -m "test(email): keep suite green after Resend wiring"
```

Otherwise skip — nothing to commit.

---

### Task 3: Document the `RESEND_API_KEY` / `EMAIL_FROM` env vars

**Files:**
- Modify: `.env.example`
- Modify: `README.md` (env-var / deployment section)

**Interfaces:**
- Consumes: nothing.
- Produces: documented config contract so the Vercel env vars (Task 5) are discoverable.

- [ ] **Step 1: Add the vars to `.env.example`**

Append to `.env.example`:

```
# Resend transactional email (notifications). Key lives in ~/Documents/resend token.rtf.
RESEND_API_KEY=re_xxxxxxxx
# Always the Resend shared sender for this pilot (no verified domain).
EMAIL_FROM=onboarding@resend.dev
# Optional: address that also receives EOI notifications (set to the Resend
# account-owner address so pilot notifications are actually deliverable).
EOI_NOTIFY_EMAILS=
```

- [ ] **Step 2: Add a short note to `README.md`**

Under the env/deployment section, add a line:

```markdown
- **Email (Resend):** notifications send via Resend from `onboarding@resend.dev`.
  Set `RESEND_API_KEY` in the environment. With no verified domain, Resend only
  reliably delivers to the Resend account-owner address (pilot limitation).
```

- [ ] **Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "docs(email): document RESEND_API_KEY and resend.dev sender limits"
```

---

### Task 4: One approved live end-to-end test send (APPROVAL-GATED)

**Files:** none (operational verification, no code change).

**Interfaces:**
- Consumes: `RESEND_API_KEY` from `~/Documents/resend token.rtf`.
- Produces: proof the key + payload actually deliver, to the Resend account-owner address only.

- [ ] **Step 1: Draft the test email and get explicit approval**

Present the exact draft to the user and WAIT for a yes:

```
From:    onboarding@resend.dev
To:      <Resend account-owner address — confirm with user>
Subject: Partner Board — Resend wiring test
Body:    This is a one-off test confirming the Partner Board can send email
         through Resend. No action needed.
```

Do not proceed without approval (standing rule; applies even to a self-addressed test).

- [ ] **Step 2: Send exactly one message after approval**

Either the Resend MCP `send email` tool, or a one-off stdlib call:

```bash
cd ~/partner-usecase-board
TOK=$(grep -oE 're_[A-Za-z0-9_]+' ~/Documents/"resend token.rtf" | head -1)
python3 -c "
import json, urllib.request, os
key='$TOK'
req=urllib.request.Request('https://api.resend.com/emails',
  data=json.dumps({'from':'onboarding@resend.dev',
    'to':['<APPROVED_RECIPIENT>'],
    'subject':'Partner Board — Resend wiring test',
    'text':'This is a one-off test confirming Resend sending works. No action needed.'}).encode(),
  method='POST',
  headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'})
import sys
with urllib.request.urlopen(req, timeout=10) as r:
    print('HTTP', r.status, r.read().decode())
"
```

Expected: `HTTP 200` with a JSON `{"id": "..."}`. Confirm the message arrives in the account-owner inbox.

- [ ] **Step 3: Record the result**

No commit. Note in the session whether delivery succeeded. If Resend returns 403/422 about the from-address or recipient, that confirms the deliverability ceiling (only the account-owner address works) — expected, not a bug.

---

### Task 5: Set `RESEND_API_KEY` in Vercel production

**Files:** none (platform config).

**Interfaces:**
- Consumes: `RESEND_API_KEY` value.
- Produces: the live app can send at runtime.

- [ ] **Step 1: Add the env var to the Vercel project**

The `vercel` CLI is not installed and npm is locked down, so use the REST API (token at `.vercel/.token`, team `team_L4jxliMIfSnjK5ls5ucK2HYP`, project `partner-usecase-board`). Add `RESEND_API_KEY` (target: production, type: encrypted) and optionally `EMAIL_FROM=onboarding@resend.dev`:

```bash
cd ~/partner-usecase-board
TOK=$(cat .vercel/.token); TEAM=team_L4jxliMIfSnjK5ls5ucK2HYP
KEY=$(grep -oE 're_[A-Za-z0-9_]+' ~/Documents/"resend token.rtf" | head -1)
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  "https://api.vercel.com/v10/projects/partner-usecase-board/env?teamId=$TEAM" \
  -d "{\"key\":\"RESEND_API_KEY\",\"value\":\"$KEY\",\"type\":\"encrypted\",\"target\":[\"production\"]}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('created:', d.get('key') or d.get('error'))"
```

Expected: `created: RESEND_API_KEY` (or a clear `already exists` error, which is fine).

- [ ] **Step 2: Redeploy so the new env var takes effect**

A new production deployment picks up the env var. Trigger via the deploy path already used for this project (git push to `vercel-neon-deploy`, or the Vercel deploy hook/MCP). Confirm afterwards with a signup smoke test that a real welcome email is attempted (check Resend dashboard "Emails" log for the send event).

- [ ] **Step 3: No commit** (platform-only change).

---

## Notes for the implementer
- The three `send_*` functions already exist and are already called from `routes_public.signup` (welcome), the admin case-create route (new-use-case), and `routes_public.respond` (new-EOI). This plan only implements the transport under them — do not touch the call sites.
- `EOI_NOTIFY_EMAILS` is already read in `routes_public.py`; setting it to the Resend account-owner address is the way to get an actually-deliverable EOI notification during the pilot.
- If the user later verifies a domain, the only change needed is `EMAIL_FROM` — no code change.
