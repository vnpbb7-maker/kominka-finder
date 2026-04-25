"""
database.py — Supabase client factory & query helpers for the kominka-finder API.
"""

from functools import lru_cache
from supabase import create_client, Client
from config import get_settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a cached Supabase client (uses anon key for read-only queries)."""
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_anon_key)


@lru_cache(maxsize=1)
def get_supabase_admin() -> Client:
    """Return a cached Supabase client with service_role key (for writes)."""
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)
