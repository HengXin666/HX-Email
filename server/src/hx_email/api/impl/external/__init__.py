from hx_email.api.impl.external.message_routes import register_external_message_routes
from hx_email.api.impl.external.pool_routes import register_external_pool_routes
from hx_email.api.impl.external.system_routes import register_external_system_routes
from hx_email.api.impl.external.temp_mail_routes import register_external_temp_mail_routes

__all__ = [
    "register_external_message_routes",
    "register_external_pool_routes",
    "register_external_system_routes",
    "register_external_temp_mail_routes",
]
