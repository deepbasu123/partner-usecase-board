"""Merged FastAPI app: public portal API + gated admin API, on Neon.

Served by one Vercel Python function. No CORS middleware (same-origin on
Vercel) and no StaticFiles mount (Vercel serves the built SPAs directly).
"""
from fastapi import FastAPI

from . import routes_public, routes_admin

app = FastAPI(title="lake Alliance — API")

app.include_router(routes_public.router)
app.include_router(routes_admin.public_router)   # /api/admin/login (unguarded)
app.include_router(routes_admin.router)          # /api/admin/* (guarded)


@app.get("/healthz")
def healthz():
    return {"ok": True}
