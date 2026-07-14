"""Vercel Python entrypoint. Exposes the merged FastAPI app as `app`.

Vercel's @vercel/python runtime loads the module-level `app` (an ASGI app) and
handles all requests routed here by vercel.json. The repo root is added to
sys.path so the `board_api` package imports cleanly from inside api/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from board_api.app import app  # noqa: E402,F401
