"""Privacy helpers for the audit trail.

Sensitive values (IP addresses, attempted login usernames) are stored as
peppered SHA-256 digests so the audit log can prove an event occurred without
exposing personal data in plaintext.
"""
import hashlib

from django.conf import settings


def hash_sensitive(value):
    """Return a peppered SHA-256 hex digest of *value*, or '' when empty.

    The site secret key acts as the pepper, so the same input always hashes
    the same way within a deployment but cannot be reversed or brute-forced
    against other deployments.
    """
    if not value:
        return ''
    raw = str(value).strip().encode('utf-8')
    return hashlib.sha256(raw + settings.SECRET_KEY.encode('utf-8')).hexdigest()