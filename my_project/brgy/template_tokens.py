"""Secret tokenized placeholders for document templates.

Readable placeholders (``{{ resident_name }}``) keep working, but staff can
also author templates with scrambled tokens (``{{ aB3xQ9Zk }}``) so a raw
``.docx`` template no longer reveals what data it pulls in.

Tokens are deterministic per (canonical field, per-document-type salt):
``HMAC-SHA256(DJANGO_SECRET_KEY, f"{salt}:{canonical}")``, base32-encoded
and truncated to :data:`TOKEN_LENGTH` chars with a guaranteed leading
letter (a valid Jinja identifier).  Nothing is stored for the map itself:
any token can be verified by recomputing it, so uploads, live-detects and
renders all agree without extra Firestore fields.
"""

import base64
import hashlib
import hmac
import re

TOKEN_LENGTH = 10

# Authoritative list of fillable fields.  Mirrors the canonical namespace
# keys built by ``_build_template_context`` in brgy/views.py (plus the
# alias targets in TEMPLATE_VAR_ALIASES).  Keep this in sync when the
# namespace gains keys.
KNOWN_CANONICAL_FIELDS = (
    'request_number',
    'request_status',
    'purpose',
    'verification_code',
    'verify_url',
    'date_today',
    'resident_name',
    'resident_full_name',
    'resident_first_name',
    'resident_middle_name',
    'resident_last_name',
    'resident_address',
    'resident_phone_number',
    'resident_contact_number',
    'resident_email',
    'resident_username',
    'resident_gender',
    'resident_civil_status',
    'resident_occupation',
    'resident_id_type',
    'resident_birth_date',
    'barangay_name',
    'barangay_address',
    'barangay_contact_number',
    'barangay_email',
    'chairman_name',
    'barangay_chairman_name',
    'document_name',
    'document_description',
    'quantity',
    'fee',
    'total_fee',
    'date_day',
    'date_month',
    'date_month_name',
    'date_year',
    'date_day_of_week',
    'resident_birth_day',
    'resident_birth_month',
    'resident_birth_month_name',
    'resident_birth_year',
    'resident_age',
)


def _normalize(name):
    return re.sub(r'[^a-z0-9]', '', str(name or '').lower())


def token_for(canonical, salt):
    """Deterministic scrambled token for ``canonical`` under ``salt``."""
    from django.conf import settings

    key = (getattr(settings, 'SECRET_KEY', '') or '').encode('utf-8')
    msg = ('%s:%s' % (salt or '', canonical)).encode('utf-8')
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    token = base64.b32encode(digest).decode('ascii').rstrip('=')
    token = token[:TOKEN_LENGTH]
    if not token or not token[0].isalpha():
        token = 'T' + token[1:]
    return token


def resolve_token(raw, salt):
    """Return the canonical field name if ``raw`` is a token, else None."""
    if not raw or not salt:
        return None
    want = _normalize(raw)
    for canonical in KNOWN_CANONICAL_FIELDS:
        if _normalize(token_for(canonical, salt)) == want:
            return canonical
    return None


def canonicalize_variables(variables, salt=''):
    """Translate detected placeholder names to canonical field names.

    Readable names pass through (normalized match against known fields);
    secret tokens are translated to their canonical field.  Unknown names
    are returned unchanged (they render blank at print time).
    """
    lookup = {_normalize(field): field for field in KNOWN_CANONICAL_FIELDS}
    out = []
    for var in (variables or []):
        name = str(var or '')
        key = _normalize(name)
        if key in lookup:
            out.append(lookup[key])
            continue
        target = resolve_token(name, salt)
        out.append(target if target else name)
    return out


def token_sheet(variables, salt):
    """[(token, canonical), ...] reference sheet for stored variables."""
    return [(token_for(var, salt), var) for var in (variables or [])]
