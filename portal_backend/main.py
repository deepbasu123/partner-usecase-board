"""FastAPI app factory for the public partner portal.

Serves the JSON API and, in the deployed container, the built React SPA
(portal-frontend/dist copied to ./static). The SPA calls only this API; DB
credentials never leave the server.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import routes_partners, routes_board, routes_responses

app = FastAPI(title="Partner Use-Case Board — Portal API")

# Credentialed CORS: the SPA sends the session cookie, so the origin must be
# explicit (not "*") when credentials are allowed. Set PORTAL_ORIGIN in prod.
_origin = os.environ.get("PORTAL_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_partners.router)
app.include_router(routes_board.router)
app.include_router(routes_responses.router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# Serve the built SPA when present (production container). Mounted last so the
# API routes above take precedence.
if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="spa")
