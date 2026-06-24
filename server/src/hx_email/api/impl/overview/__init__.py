"""Overview API routes package.

Provides system-wide statistics endpoints for the admin dashboard.
"""

from hx_email.api.impl.overview.overview_refresh_routes import (
    register_overview_refresh_routes,
)
from hx_email.api.impl.overview.overview_routes import register_overview_routes

__all__ = ["register_overview_refresh_routes", "register_overview_routes"]
