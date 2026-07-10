"""FastAPI app factory for the admin cockpit (Databricks App, behind SSO).

Serves the admin JSON API and the built admin React UI (frontend/dist copied
to ./static in the deploy step). No auth logic here — the platform's workspace
SSO gates all access.
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import routes_admin

app = FastAPI(title="Partner Use-Case Board — Admin")

app.include_router(routes_admin.router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="admin-spa")
