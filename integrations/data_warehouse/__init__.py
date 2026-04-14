"""
integrations/data_warehouse/__init__.py
Exports the two key public surfaces: DB initialiser + DAL.
"""

from .sqlite_client import init_db, get_db_connection
from . import vendor_db

__all__ = ["init_db", "get_db_connection", "vendor_db"]
