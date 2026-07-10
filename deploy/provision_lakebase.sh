#!/usr/bin/env bash
# Apply the board schema + seed to an EXISTING Lakebase instance.
#
# We reuse an existing instance (do not provision a new one). List instances with:
#   TOKEN=$(databricks auth token -p <profile> | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
#   curl -s -H "Authorization: Bearer $TOKEN" "$HOST/api/2.0/database/instances" | python3 -m json.tool
#
# Then export connection env (host from read_write_dns, a minted credential as
# PGPASSWORD) and run this script. The credential is minted via the workspace:
#   POST $HOST/api/2.0/database/credentials  {"instance_names":["<inst>"],"request_id":"provision"}
#
# NOTE: Databricks CLI v0.228.0 has no `database` command group, so we go via
# REST. A newer CLI can use `databricks database ...` instead.
set -euo pipefail

: "${PGHOST:?export PGHOST (instance read_write_dns)}"
: "${PGUSER:?export PGUSER (your Databricks user or SP client id)}"
: "${PGPASSWORD:?export PGPASSWORD (minted Lakebase credential token)}"
PGDATABASE="${PGDATABASE:-databricks_postgres}"
PGPORT="${PGPORT:-5432}"

CONN="sslmode=require host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

echo "Applying schema to $PGHOST/$PGDATABASE ..."
psql "$CONN" -v ON_ERROR_STOP=1 -f "$HERE/db/schema.sql"
echo "Applying seed ..."
psql "$CONN" -v ON_ERROR_STOP=1 -f "$HERE/db/seed.sql"
echo "Done. Tables:"
psql "$CONN" -c "\dt"
