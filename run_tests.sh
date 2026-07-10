#!/usr/bin/env bash
# Run the portal-backend test suite against an ephemeral local Postgres 16.
# Mirrors Lakebase (PG_VERSION_16) closely enough to validate the real SQL.
set -euo pipefail

PGBIN=/opt/homebrew/opt/postgresql@16/bin
export PGDATA=/tmp/pub_pgtest
PORT=5433
HERE="$(cd "$(dirname "$0")" && pwd)"

# (Re)create the ephemeral cluster.
"$PGBIN/pg_ctl" -D "$PGDATA" stop >/dev/null 2>&1 || true
rm -rf "$PGDATA"
"$PGBIN/initdb" -D "$PGDATA" -U postgres --auth=trust >/tmp/initdb.log 2>&1
"$PGBIN/pg_ctl" -D "$PGDATA" -o "-p $PORT -k /tmp -c listen_addresses=''" -l /tmp/pg.log start >/dev/null
sleep 2
"$PGBIN/psql" -h /tmp -p $PORT -U postgres -c "CREATE DATABASE board;" >/dev/null
"$PGBIN/psql" -h /tmp -p $PORT -U postgres -d board -v ON_ERROR_STOP=1 -f "$HERE/db/schema.sql" >/dev/null
"$PGBIN/psql" -h /tmp -p $PORT -U postgres -d board -v ON_ERROR_STOP=1 -f "$HERE/db/seed.sql" >/dev/null

# Point db.py at the local cluster.
export PGHOST=/tmp PGPORT=$PORT PGUSER=postgres PGPASSWORD=x PGDATABASE=board \
       PGSSLMODE=disable LAKEBASE_INSTANCE=local-test SESSION_SECRET=test-secret

# shellcheck disable=SC1091
. "$HERE/.venv/bin/activate"
cd "$HERE"
python -m pytest portal_backend/tests/ "$@"
RC=$?

"$PGBIN/pg_ctl" -D "$PGDATA" stop >/dev/null 2>&1 || true
exit $RC
