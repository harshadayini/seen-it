"""Seen It Python backend package root.

What this module does:
    Marks `backend` as an explicit Python package so modules across
    `backend/matching/`, `backend/shopify/`, `backend/video/`, and `eval/`
    resolve `backend.*` imports consistently across unittest, pytest, and FastAPI.

Use cases:
    - Package resolution for `backend.config`, `backend.matching`, and `backend.shopify`.

What this module must NOT do:
    - Must not execute side-effectful startup logic or network requests on import.
"""
