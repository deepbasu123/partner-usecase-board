#!/usr/bin/env bash
# Vercel build: assemble the single SPA into dist/ (portal is now role-gated).
# The Python API (api/index.py) is auto-detected by Vercel as a serverless
# function and is not built here.
set -euo pipefail

# The committed package-lock.json files were generated on macOS and omit
# rollup's Linux-only optional deps (@rollup/rollup-linux-x64-gnu), which makes
# npm crash on Vercel's Linux builder ("Invalid Version:" in arborist dedupe).
# Remove the lockfile in the build sandbox so npm resolves the correct platform
# binaries fresh. Versions in package.json are exact-pinned for determinism, and
# this only touches the ephemeral build copy — the committed lockfiles stay.

echo "── building portal-frontend (single unified app) ──"
( cd portal-frontend && rm -f package-lock.json && npm install --no-audit --no-fund && npm run build )

echo "── assembling dist/ ──"
rm -rf dist
cp -r portal-frontend/dist dist

echo "── dist/ contents ──"
ls -la dist
