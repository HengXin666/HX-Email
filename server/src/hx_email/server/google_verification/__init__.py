"""Google Search Console HTML-file site verification.

Owners can upload the ``google<hash>.html`` file Google issues for domain
verification through the admin settings UI. The file is stored under the
instance data directory and served back at the exact site-root URL Google
fetches (e.g. ``https://<host>/google18261d952ce2f02c.html``) without auth.
"""

from hx_email.server.google_verification.policy import validate_verification_file
from hx_email.server.google_verification.storage import (
    delete_verification_file,
    list_verification_files,
    resolve_verification_file,
    save_verification_file,
    verification_dir,
)

__all__ = [
    "delete_verification_file",
    "list_verification_files",
    "resolve_verification_file",
    "save_verification_file",
    "validate_verification_file",
    "verification_dir",
]
