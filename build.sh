#!/usr/bin/env bash
# Vercel build: assemble both SPAs into one output dir (dist/).
#   portal → dist/           (served at /)
#   admin  → dist/admin/      (served at /admin, Vite base=/admin/)
# The Python API (api/index.py) is auto-detected by Vercel as a serverless
# function and is not built here.
set -euo pipefail

echo "── building portal-frontend ──"
npm --prefix portal-frontend ci
npm --prefix portal-frontend run build          # -> portal-frontend/dist

echo "── building admin-app/frontend ──"
npm --prefix admin-app/frontend ci
npm --prefix admin-app/frontend run build        # -> admin-app/frontend/dist (base=/admin/)

echo "── assembling dist/ ──"
rm -rf dist
cp -r portal-frontend/dist dist
mkdir -p dist/admin
cp -r admin-app/frontend/dist/* dist/admin/

echo "── dist/ contents ──"
ls -la dist
ls -la dist/admin
