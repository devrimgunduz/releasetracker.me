"""Ensure required settings exist before any app module is imported.

Some modules (e.g. app.db) build objects from Settings at import time, which
needs SECRET_KEY and DATABASE_URL. These dummy values let pure unit tests import
freely; the async engine is created lazily and never actually connects here.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-1234567890")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://radar:radar@localhost:5432/radar"
)
