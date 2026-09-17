import csv
import io
import logging
import os
import random
import re
import secrets
import string
from datetime import datetime, date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.core.signing import TimestampSigner
from django.core.validators import validate_email
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from docxtpl import DocxTemplate
import mammoth

from . import firestore_db
from . import template_tokens
from .auth import login_user, logout_user
from .security import hash_sensitive

logger = logging.getLogger(__name__)
from .forms import (
    CustomAuthForm, ResidentRegistrationForm, StaffCreationForm, BarangayForm,
    DocumentTypeForm, GlobalTypeOverrideForm, RejectForm, UpdateStatusForm,
    StaffProfileForm, ChangePasswordForm, RequestPasswordResetForm, SetNewPasswordForm,
    MarkPaymentForm, AnnouncementForm, OTPVerificationForm,
)
from .models import (
    ActivityLog, Announcement, Barangay, CustomUser, DocumentRequest, DocumentRequestItem,
    DocumentType, DocumentTypeOverride, Notification,
    get_announcement, get_barangay, get_document_request, get_document_type, get_document_type_override,
    get_override_for, get_request_items, get_user,
)
from .forms import (
    IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, TEMPLATE_EXTENSIONS, MAX_TEMPLATE_SIZE,
    REQUIREMENT_EXTENSIONS, MAX_REQUIREMENT_FILE_SIZE, _save_uploaded_file,
)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in roles:
                messages.error(request, 'You do not have permission to access that page.')
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def log_activity(user, action, details='', request=None, subject_user_id=None):
    ip = request.META.get('REMOTE_ADDR') if request else None
    firestore_db.create_activity_log({
        'user_id': user.pk if user else None,
        'barangay_id': user.barangay_id if user else None,
        'action': action,
        'details': details,
        'ip_hash': hash_sensitive(ip),
        'subject_user_id': subject_user_id,
    })


def notify(user_id, title, message, link=''):
    firestore_db.create_notification({
        'user_id': user_id,
        'title': title,
        'message': message,
        'link': link,
        'is_read': False,
    })


def notify_admins(title, message, link=''):
    """Notify every active admin account."""
    for admin in firestore_db.list_users(filters=[('role', '==', 'admin')]):
        if admin.get('is_active', True):
            notify(admin['id'], title, message, link)


def send_user_email(user, subject, body):
    """Send an email to a user. Returns True only when delivery succeeded.

    SMTP errors are logged (not silently swallowed) so failures such as a bad
    app password surface in the server console instead of being hidden.
    """
    if not getattr(settings, 'EMAIL_HOST', None):
        logger.warning('Email send skipped: EMAIL_HOST is not configured.')
        return False
    email = (getattr(user, 'email', '') or '').strip()
    if not email:
        logger.warning('Email send skipped: user has no email address.')
        return False
    try:
        sent = send_mail(
            subject,
            body,
            getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'no-reply@barangay.local',
            [email],
            fail_silently=False,
        )
        if not sent:
            logger.error('Email send reported 0 messages delivered to %s.', email)
            return False
        return True
    except Exception:
        logger.exception('Email delivery failed to %s.', email)
        return False


def _absolute_url(request, path):
    """Absolute URL for a path; falls back to settings.SITE_URL when no request."""
    if request is not None:
        return request.build_absolute_uri(path)
    base = getattr(settings, 'SITE_URL', '') or ''
    return base + path


def _make_verification_code(length=12):
    """Generate a cryptographically secure public verification reference code."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _normalize_template_var(name):
    """Normalize a placeholder name for matching (case/punctuation insensitive)."""
    return re.sub(r'[^a-z0-9]', '', str(name or '').lower())


# Ambiguous short placeholder names (normalized) mapped to canonical keys.
TEMPLATE_VAR_ALIASES = {
    'name': 'resident_name',
    'fullname': 'resident_name',
    'resident': 'resident_name',
    'date': 'date_today',
    'today': 'date_today',
    'datetoday': 'date_today',
    'address': 'resident_address',
    'requestno': 'request_number',
    'requestnum': 'request_number',
    'ref': 'verification_code',
    'refno': 'verification_code',
    'referenceno': 'verification_code',
    'reference': 'verification_code',
    'referencecode': 'verification_code',
    'referencenumber': 'verification_code',
    'verification': 'verification_code',
    'verifycode': 'verification_code',
    'code': 'verification_code',
    'verifyurl': 'verify_url',
    'verificationlink': 'verify_url',
    'verifylink': 'verify_url',
    'docname': 'document_name',
    'document': 'document_name',
    'doctype': 'document_name',
    'documenttype': 'document_name',
    'chairman': 'chairman_name',
    'barangaychairman': 'chairman_name',
    'barangay': 'barangay_name',
    'age': 'resident_age',
    'dayofweek': 'date_day_of_week',
    'weekday': 'date_day_of_week',
}


def _format_template_date(value, fmt='%B %d, %Y'):
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        try:
            return value.strftime(fmt)
        except Exception:
            return ''
    return value


def _as_template_date(value):
    """Normalize a value to a ``date`` best-effort (or None).

    Accepts ``date``/``datetime`` and common string forms; anything else
    (missing/garbled birth dates) yields None so placeholders render blank.
    """
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%B %d, %Y', '%b %d, %Y',
                    '%d/%m/%Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(text, fmt).date()
            except (ValueError, TypeError):
                pass
    return None


def _precise_age(birth_value):
    """Whole years lived as of today; '' when the birth date is unknown."""
    born = _as_template_date(birth_value)
    if born is None:
        return ''
    today = timezone.localdate()
    years = today.year - born.year - (
        (today.month, today.day) < (born.month, born.day)
    )
    return str(years) if years >= 0 else ''


def _build_template_context(resident=None, barangay=None, doc_req=None, item=None,
                            doc_type=None, purpose='', request_number='',
                            verification_code='', verify_url=''):
    """Build the flat value namespace used to render document templates.

    Canonical placeholder values (``resident_name``, ``purpose``,
    ``date_today``, ``verification_code``, …) are keyed by their exact
    names; ``_resolve_template_context`` additionally maps any custom
    placeholder a template may use (exact or aliased).
    """
    if doc_req is not None:
        request_number = request_number or getattr(doc_req, 'request_number', '') or ''
        purpose = purpose or getattr(doc_req, 'purpose', '') or ''
    contact = ''
    if resident is not None:
        contact = getattr(resident, 'phone_number', '') or ''
    if not contact and doc_req is not None:
        contact = getattr(doc_req, 'contact_number', '') or ''
    fee_value = None
    if item is not None:
        fee_value = getattr(item, 'fee_per_unit', None)
    if fee_value is None and doc_type is not None:
        fee_value = getattr(doc_type, 'fee', None)
    quantity = getattr(item, 'quantity', '') if item is not None else ''
    try:
        total_fee = float(fee_value) * int(quantity or 0) if fee_value not in (None, '') else ''
    except (TypeError, ValueError):
        total_fee = ''
    chairman = getattr(barangay, 'chairman_name', '') or '' if barangay is not None else ''
    full_name = getattr(resident, 'display_name', '') or '' if resident is not None else ''
    today = timezone.localdate()
    birth = _as_template_date(
        getattr(resident, 'birth_date', None) if resident is not None else None
    )
    return {
        # Request
        'request_number': request_number or '',
        'request_status': getattr(doc_req, 'status', '') or '' if doc_req is not None else '',
        'purpose': purpose or '',
        # Verification reference
        'verification_code': verification_code or '',
        'verify_url': verify_url or '',
        # Dates (issuance)
        'date_today': today.strftime('%B %d, %Y'),
        'date_day': today.strftime('%d'),
        'date_month': today.strftime('%m'),
        'date_month_name': today.strftime('%B'),
        'date_year': today.strftime('%Y'),
        'date_day_of_week': today.strftime('%A'),
        # Resident
        'resident_name': full_name,
        'resident_full_name': full_name,
        'resident_first_name': getattr(resident, 'first_name', '') or '' if resident is not None else '',
        'resident_middle_name': getattr(resident, 'middle_name', '') or '' if resident is not None else '',
        'resident_last_name': getattr(resident, 'last_name', '') or '' if resident is not None else '',
        'resident_address': getattr(resident, 'address', '') or '' if resident is not None else '',
        'resident_phone_number': getattr(resident, 'phone_number', '') or '' if resident is not None else '',
        'resident_contact_number': contact,
        'resident_email': getattr(resident, 'email', '') or '' if resident is not None else '',
        'resident_username': getattr(resident, 'username', '') or '' if resident is not None else '',
        'resident_gender': getattr(resident, 'gender', '') or '' if resident is not None else '',
        'resident_civil_status': getattr(resident, 'civil_status', '') or '' if resident is not None else '',
        'resident_occupation': getattr(resident, 'occupation', '') or '' if resident is not None else '',
        'resident_id_type': getattr(resident, 'id_type', '') or '' if resident is not None else '',
        'resident_birth_date': birth.strftime('%B %d, %Y') if birth else '',
        'resident_birth_day': birth.strftime('%d') if birth else '',
        'resident_birth_month': birth.strftime('%m') if birth else '',
        'resident_birth_month_name': birth.strftime('%B') if birth else '',
        'resident_birth_year': birth.strftime('%Y') if birth else '',
        'resident_age': _precise_age(birth),
        # Barangay
        'barangay_name': getattr(barangay, 'name', '') or '' if barangay is not None else '',
        'barangay_address': getattr(barangay, 'address', '') or '' if barangay is not None else '',
        'barangay_contact_number': getattr(barangay, 'contact_number', '') or '' if barangay is not None else '',
        'barangay_email': getattr(barangay, 'email', '') or '' if barangay is not None else '',
        'chairman_name': chairman,
        'barangay_chairman_name': chairman,
        # Document / item
        'document_name': getattr(doc_type, 'name', '') or '' if doc_type is not None else '',
        'document_description': getattr(doc_type, 'description', '') or '' if doc_type is not None else '',
        'quantity': quantity or '',
        'fee': fee_value if fee_value is not None else '',
        'total_fee': total_fee,
    }


def _resolve_template_context(namespace, variables, token_salt=''):
    """Resolve every detected template placeholder to a value.

    Starts from the full canonical namespace (so legacy placeholders keep
    working) and adds alias/exact matches for any custom placeholder the
    template uses.  Secret tokens (see ``brgy.template_tokens``) are
    translated to their canonical field when ``token_salt`` is given.
    Unmappable placeholders render blank (lenient Jinja).
    """
    context = dict(namespace)
    by_norm = {_normalize_template_var(key): value for key, value in namespace.items()}
    for var in (variables or []):
        key = _normalize_template_var(var)
        if key in by_norm:
            context[var] = by_norm[key]
            continue
        target = TEMPLATE_VAR_ALIASES.get(key)
        if target:
            context[var] = namespace.get(target, '')
            continue
        if token_salt:
            canonical = template_tokens.resolve_token(var, token_salt)
            if canonical and canonical in namespace:
                context[var] = namespace[canonical]
    return context


def _doc_template_salt(doc_type):
    """Per-document-type salt used for secret placeholder tokens."""
    salt = getattr(doc_type, 'template_salt', '') or ''
    if not salt:
        salt = str(getattr(doc_type, 'pk', '') or '')
    return salt


def _sheet_variables(doc_type, override=None):
    """Canonical placeholder names for display: stored, else live-detected.

    Legacy document types predate upload-time detection, so their stored
    ``template_variables`` may be empty even though a template file exists;
    in that case detect from the file directly.
    """
    stored = _template_detected_variables(doc_type, override)
    if stored:
        return stored
    holder = override if (
        override is not None and getattr(override, 'has_template', False)
    ) else doc_type
    template_path = None
    tpl = getattr(holder, 'template_file', None)
    if tpl is not None:
        try:
            template_path = tpl.path
        except Exception:
            template_path = None
    if not template_path or not os.path.exists(template_path):
        return []
    return _live_template_variables(template_path, _doc_template_salt(doc_type))


def _token_sheet(doc_type, override=None):
    """[(token, canonical)] reference sheet for a type's placeholders.

    Uses the override's variables when it has its own template, otherwise
    the parent type's.  Tokens are computed under the parent type's salt.
    """
    stored = _sheet_variables(doc_type, override)
    salt = _doc_template_salt(doc_type)
    if not stored or not salt:
        return []
    return template_tokens.token_sheet(stored, salt)


def _inject_token_values(context, namespace, doc_type, override=None):
    """Add every secret-token placeholder to the render context.

    The stored ``template_variables`` are canonical names, but a template
    may be authored with the raw tokens themselves (``{{ aB3xQ9Zk }}``).
    Injecting the whole sheet guarantees both spellings fill, regardless
    of which list ``variables`` carried.
    """
    for tok, field in _token_sheet(doc_type, override):
        if tok not in context:
            context[tok] = namespace.get(field, '')
    return context


def _live_template_variables(template_path, token_salt=''):
    """Detect placeholder names in a saved template file (best effort).

    Returns the raw names found plus their canonical translations, so both
    readable and secret-token spellings can be resolved at render time.
    """
    try:
        raw = sorted(
            str(v) for v in DocxTemplate(template_path).get_undeclared_template_variables()
        )
        return sorted(set(raw) | set(
            template_tokens.canonicalize_variables(raw, token_salt)
        ))
    except Exception:
        return []


def _template_detected_variables(doc_type, override=None):
    """Stored placeholder list, or None when unknown (caller live-detects)."""
    for obj in (override, doc_type):
        if obj is None:
            continue
        stored = getattr(obj, 'template_variables', None)
        if stored:
            return list(stored)
    return None


def _item_verification_code(item, doc_req):
    """Per-document verification reference: item code, then legacy request code."""
    code = getattr(item, 'verification_code', None) if item is not None else None
    if not code and doc_req is not None:
        code = getattr(doc_req, 'verification_code', None)
    return code or ''


# Password-reset links expire after 30 minutes and are bound to the user's
# current password hash, so a used or pre-empted link cannot be reused.
PASSWORD_RESET_TIMEOUT = 60 * 30
PASSWORD_RESET_SALT = 'brgy.password_reset'


def _make_reset_token(user):
    value = f"{user.pk}:{user.get_session_auth_hash()}"
    return TimestampSigner(salt=PASSWORD_RESET_SALT).sign(value)


def _parse_reset_token(token):
    """Return the CustomUser for a valid reset token, else None."""
    try:
        value = TimestampSigner(salt=PASSWORD_RESET_SALT).unsign(
            token, max_age=PASSWORD_RESET_TIMEOUT
        )
        pk, _, auth_hash = value.partition(':')
        user = get_user(pk)
        if user is None:
            return None
        if user.get_session_auth_hash() != auth_hash:
            return None
        return user
    except Exception:
        return None


def send_welcome_email(email, display_name, password):
    """Send staff credentials by email. Returns True only on successful delivery."""
    if not getattr(settings, 'EMAIL_HOST', None):
        logger.warning('Welcome email skipped: EMAIL_HOST is not configured.')
        return False
    if not (email or '').strip():
        logger.warning('Welcome email skipped: no recipient email given.')
        return False
    subject = 'Your Barangay System Staff Account'
    body = (
        f'Hi {display_name},\n\n'
        f'Your staff account has been created on the Barangay Document System.\n'
        f'Username: {email.split("@")[0]}\n'
        f'Temporary password: {password}\n\n'
        f'Please sign in and change your password on your first login.\n\n'
        f'Share this email securely with the staff member only.'
    )
    try:
        sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL or 'no-reply@barangay.local', [email], fail_silently=False)
        if not sent:
            logger.error('Welcome email reported 0 messages delivered to %s.', email)
            return False
        return True
    except Exception:
        logger.exception('Welcome email delivery failed to %s.', email)
        return False


def notifications_url_name(user):
    if user.role == 'admin':
        return 'admin_notifications'
    if user.role == 'staff':
        return 'staff_notifications'
    return 'notifications'


def staff_of_barangay(barangay_id):
    users = firestore_db.list_users(filters=[('role', '==', 'staff')])
    return [
        u for u in users
        if u.get('barangay_id') == barangay_id and u.get('is_active')
    ]


def requests_for_barangay(barangay_id):
    """Document requests whose resident belongs to the given barangay."""
    requests = firestore_db.list_document_requests()
    resident_ids = {
        req.get('resident_id') for req in requests if req.get('resident_id')
    }
    residents = firestore_db.get_users_bulk(resident_ids)
    result = []
    for req in requests:
        resident = residents.get(req.get('resident_id'))
        if resident and resident.get('barangay_id') == barangay_id:
            result.append(DocumentRequest(req))
    return result


def _request_search_text(req):
    resident = req.resident
    parts = [req.request_number or '']
    if resident:
        parts += [resident.first_name or '', resident.last_name or '', resident.email or '']
    for item in req.items.all():
        doc_type = item.document_type
        if doc_type:
            parts.append(doc_type.name or '')
    return ' '.join(str(part) for part in parts).lower()


def _brgy_or_404(pk):
    brgy = get_barangay(pk)
    if not brgy:
        raise Http404
    return brgy


def _user_or_404(pk):
    user = get_user(pk)
    if not user:
        raise Http404
    return user


def _doc_type_or_404(pk):
    doc_type = get_document_type(pk)
    if not doc_type:
        raise Http404
    return doc_type


def _delete_template_file(doc_type):
    path = getattr(doc_type.template_file, 'path', '')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _request_or_404(pk):
    req = get_document_request(pk)
    if not req:
        raise Http404
    return req


def _apply_status_transition(doc_request, new_status, user, request=None, notes='', rejection_reason='',
                             pickup_date=None, pickup_slot=None):
    """Persist a document request status change and notify/resident-log it.

    Returns the human readable display label of the new status, or None if
    the status did not actually change.
    """
    current = doc_request.status
    if new_status == current:
        return None

    updates = {'status': new_status, 'processed_by_id': user.pk}
    now = firestore_db.utcnow()
    if new_status == 'approved' and not doc_request.approved_at:
        updates['approved_at'] = now
    elif new_status == 'printed' and not doc_request.printed_at:
        updates['printed_at'] = now
    elif new_status == 'ready_for_pickup' and not doc_request.ready_at:
        updates['ready_at'] = now
    elif new_status == 'completed' and not doc_request.completed_at:
        updates['completed_at'] = now
    if notes:
        updates['staff_notes'] = notes
    if new_status == 'rejected' and rejection_reason:
        updates['rejection_reason'] = rejection_reason
    if new_status == 'ready_for_pickup':
        valid_slots = dict(DocumentRequest.PickupSlot.choices)
        if pickup_slot in valid_slots:
            updates['pickup_slot'] = pickup_slot
        if pickup_date is not None:
            updates['pickup_date'] = pickup_date
    firestore_db.update_document_request(doc_request.pk, updates)

    doc_names = ', '.join(
        item.document_type.name for item in doc_request.items.all()
        if item.document_type
    ) or 'documents'
    status_messages = {
        'approved': f'Your request for {doc_names} has been approved.',
        'printed': f'Your document(s) [{doc_names}] have been printed and are being prepared for pickup.',
        'ready_for_pickup': f'Your document(s) [{doc_names}] is/are ready for pickup.',
        'completed': f'Your request for {doc_names} has been completed.',
        'rejected': f'Your request for {doc_names} has been rejected.',
        'cancelled': f'Your request for {doc_names} has been cancelled.',
    }
    new_display = dict(DocumentRequest.Status.choices).get(new_status, new_status)
    status_message = status_messages.get(
        new_status, f'Your request status has been updated to {new_display}.'
    )
    if new_status == 'ready_for_pickup' and pickup_date is not None:
        slot_label = dict(DocumentRequest.PickupSlot.choices).get(
            pickup_slot, ''
        ) if pickup_slot in dict(DocumentRequest.PickupSlot.choices) else ''
        status_message += (
            f' Pickup is scheduled for {pickup_date:%A, %B %d, %Y}'
            + (f' ({slot_label}).' if slot_label else '.')
        )
    if new_status == 'rejected' and rejection_reason:
        status_message += f' Reason: {rejection_reason}'
    notify(
        doc_request.resident_id,
        f'Request {new_display}',
        status_message,
        link=reverse('request_history'),
    )
    resident = doc_request.resident
    if resident is not None:
        send_user_email(
            resident,
            f'Request {new_display}',
            f'{status_message}\n\n'
            f'Request Number: {doc_request.request_number}\n'
            f'Track it here: {_absolute_url(request, "/resident/history/")}',
        )
    log_activity(user, f'Request Status Updated: {new_display}',
                 f'{doc_request.request_number} changed from {current} to {new_status}.', request,
                 subject_user_id=doc_request.resident_id)
    return new_display


def _item_or_404(pk):
    item = firestore_db.get_document_request_item(pk)
    if not item:
        raise Http404
    return DocumentRequestItem(item)


def _next_statuses(current):
    """Return the list of valid next statuses for a document request.

    Enforces a sequential workflow: a request can only move forward one step
    at a time (or be rejected) — no skipping ahead or rolling back.
    """
    allowed = {
        'pending': ['approved', 'rejected'],
        'approved': ['printed', 'ready_for_pickup', 'rejected'],
        'printed': ['ready_for_pickup', 'rejected'],
        'ready_for_pickup': ['completed', 'rejected'],
    }
    if current in allowed:
        return allowed[current]
    return []


def _status_choices_for(current):
    """(value, label) choices usable by a Django ChoiceField."""
    labels = dict(DocumentRequest.Status.choices)
    return [(s, labels[s]) for s in _next_statuses(current) if s in labels]


# ═══════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════

def home_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'brgy/home.html')


def services_page(request):
    doc_types = []
    for d in firestore_db.list_document_types(
        filters=[('is_active', '==', True)],
        order_by='name',
    ):
        dt = DocumentType(d)
        barangay = dt.barangay
        if not dt.is_global:
            if barangay is None or not getattr(barangay, 'is_active', True):
                continue
        doc_types.append(dt)
    return render(request, 'brgy/services.html', {
        'doc_types': doc_types,
        'page_title': 'Services',
    })


def about_page(request):
    return render(request, 'brgy/about.html', {
        'page_title': 'About',
    })


# A verification reference is accepted once the document has been printed.
_VERIFY_OK_STATUSES = ('printed', 'ready_for_pickup', 'completed')


def verify_document_view(request):
    code = request.GET.get('code', '').strip().upper()
    doc_request = None
    doc_item = None
    doc_type = None
    error = None

    if code:
        matches = firestore_db.list_document_request_items(
            filters=[('verification_code', '==', code)]
        )
        if matches:
            doc_item = DocumentRequestItem(matches[0])
            request_data = firestore_db.get_document_request(doc_item.request_id)
            doc_request = DocumentRequest(request_data) if request_data else None
        if doc_request is None:
            # Legacy fallback: request-level codes issued before per-document codes.
            requests = firestore_db.list_document_requests(
                filters=[('verification_code', '==', code)]
            )
            if requests:
                doc_request = DocumentRequest(requests[0])
        if doc_request is None:
            error = "Invalid verification code. This document is not recognized by the system."
        elif doc_request.status in ('cancelled', 'rejected'):
            error = "This document is no longer valid (it was cancelled or rejected)."
        elif doc_request.status not in _VERIFY_OK_STATUSES and not (
            doc_item is not None and doc_item.is_printed
        ):
            error = "This document exists but has not been printed/issued yet."
        elif doc_item is not None:
            doc_type = doc_item.document_type

    return render(request, 'brgy/verify.html', {
        'page_title': 'Verify Document',
        'doc_request': doc_request,
        'doc_item': doc_item,
        'doc_type': doc_type,
        'verification_code': code,
        'query': code,
        'error': error,
    })


def _login_rate_key(request, username):
    """Build a stable key for rate limiting (hashed username + client IP)."""
    ip = request.META.get('REMOTE_ADDR') or 'unknown'
    return f"{hash_sensitive(username)}|{hash_sensitive(ip)}"


def password_reset(request):
    """Request a password-reset email for an existing, active account."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RequestPasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].strip().lower()
            user = None
            for u in firestore_db.list_users(filters=[('email', '==', email)]):
                if u.get('is_active'):
                    user = CustomUser(u)
                    break
            if user is not None:
                token = _make_reset_token(user)
                reset_url = _absolute_url(
                    None, reverse('password_reset_confirm', args=[token])
                )
                subject = 'Reset your Barangay Document System password'
                body = (
                    f'Hi {user.display_name},\n\n'
                    'You recently requested a password reset for your Barangay '
                    'Document System account.\n\n'
                    f'Reset your password here: {reset_url}\n\n'
                    'This link expires in 30 minutes and can only be used once. '
                    'If you did not request this, you can safely ignore this email.'
                )
                sent = send_user_email(user, subject, body)
                if not sent and settings.DEBUG:
                    messages.add_message(
                        request,
                        messages.WARNING,
                        'Email is not configured, so the reset link is shown here '
                        f'(DEVELOPMENT ONLY): <a href="{reset_url}">{reset_url}</a>',
                        extra_tags='safe',
                    )
                log_activity(None, 'Password Reset Requested',
                             'Password reset link issued.', request,
                             subject_user_id=user.pk)
            messages.success(
                request,
                'If an account exists for that email, you will receive a link '
                'to reset your password shortly.'
            )
            return redirect('login')
        messages.error(request, 'Please enter a valid email address.')
        return render(request, 'brgy/password_reset.html', {
            'form': form, 'page_title': 'Reset Password',
        })
    form = RequestPasswordResetForm()
    return render(request, 'brgy/password_reset.html', {
        'form': form, 'page_title': 'Reset Password',
    })


def password_reset_confirm(request, token):
    """Validate a signed reset token and let the user set a new password."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    user = _parse_reset_token(token)
    if user is None:
        messages.error(
            request,
            'This password reset link is invalid or has expired. Please request a new one.'
        )
        return redirect('password_reset')
    if request.method == 'POST':
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            firestore_db.update_user(user.pk, {'password': make_password(new_password)})
            refreshed = get_user(user.pk)
            login_user(request, refreshed)
            log_activity(refreshed, 'Password Reset', 'Password reset via email link.', request)
            notify(refreshed.pk, 'Password Reset',
                   'Your password has been reset successfully.', link=reverse('resident_dashboard'))
            messages.success(request, 'Your password has been reset. Welcome back!')
            return redirect('dashboard')
        return render(request, 'brgy/password_reset_confirm.html', {
            'form': form, 'page_title': 'Set New Password',
        })
    form = SetNewPasswordForm()
    return render(request, 'brgy/password_reset_confirm.html', {
        'form': form, 'page_title': 'Set New Password',
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = CustomAuthForm()
    if request.method == 'POST':
        form = CustomAuthForm(request=request, data=request.POST)
        username = request.POST.get('username', '')
        rate_key = _login_rate_key(request, username)

        # Rate limiting runs BEFORE credential checks so a locked key is
        # rejected outright (even with correct credentials).  CustomAuthForm
        # deliberately skips AuthenticationForm's internal authenticate() so a
        # failed login still reaches the rate-limiting code below.
        if firestore_db.is_login_locked(rate_key):
            remaining = firestore_db.login_attempts_remaining(rate_key)
            messages.error(
                request,
                'Too many failed login attempts. Please wait a few minutes and try again.'
            )
            log_activity(None, 'Login Blocked',
                         f'Login blocked (lockout) for username hash '
                         f'{hash_sensitive(username)}.', request)
            form.add_error(None, 'Too many failed attempts. Please try again later.')
            return render(request, 'brgy/login.html', {'form': form, 'page_title': 'Sign In'})

        if form.is_valid():
            from .auth import FirestoreBackend
            user = FirestoreBackend().authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None:
                firestore_db.clear_failed_logins(rate_key)
                log_activity(user, 'User Login', 'Password verified, OTP sent.', request)
                if not _send_login_otp(request, user):
                    # OTP could not be delivered; do not hand out a session.
                    form.add_error(None, 'We could not send a One-Time PIN. Please try again later.')
                    return render(request, 'brgy/login.html', {'form': form, 'page_title': 'Sign In'})
                # Complete authentication is deferred until the OTP is verified.
                request.session['otp_user_id'] = str(user.pk)
                next_url = request.GET.get('next')
                if next_url:
                    from urllib.parse import urlencode
                    return redirect(
                        reverse('verify_otp') + '?' + urlencode({'next': next_url})
                    )
                return redirect('verify_otp')

        # Bad credentials (or a missing field): record the failure so repeated
        # attempts eventually lock the key.  Empty usernames are not credited.
        form.add_error(None, 'Invalid username or password.')
        if username:
            firestore_db.record_failed_login(rate_key)
            remaining = firestore_db.login_attempts_remaining(rate_key)
            log_activity(None, 'Login Failed',
                         'Failed login attempt for username hash '
                         f'{hash_sensitive(username)}.', request)
            if remaining is None:
                messages.error(
                    request,
                    'Too many failed login attempts. Please wait a few minutes and try again.'
                )
                form.add_error(None, 'Too many failed attempts. Please try again later.')
    return render(request, 'brgy/login.html', {'form': form, 'page_title': 'Sign In'})


def _generate_otp():
    """Return a fresh 6-digit numeric OTP (always zero-padded)."""
    return f'{secrets.randbelow(10 ** 6):06d}'


def _mask_email(email):
    """Mask an email for display, e.g. john.doe@x.com -> j***e@x.com."""
    email = (email or '').strip()
    if not email or '@' not in email:
        return ''
    local, _, domain = email.partition('@')
    if not local:
        return email
    return f'{local[0]}***{local[-1]}@{domain}'


def _send_login_otp(request, user):
    """Generate, persist and email a login OTP for *user*.

    Returns True only when the email was actually delivered; otherwise the
    OTP record is discarded and the login is aborted so a session is never
    handed out without the code reaching the user's inbox.
    """
    otp = _generate_otp()
    firestore_db.create_otp(user.pk, otp)
    email = (getattr(user, 'email', '') or '').strip()

    if not email:
        firestore_db.delete_otp(user.pk)
        return False

    subject = 'Your Barangay System login code'
    body = (
        f'Hi {user.display_name},\n\n'
        f'Your one-time login code is: {otp}\n\n'
        'This code expires in 10 minutes. Do not share it with anyone. '
        'If you did not try to sign in, you can safely ignore this email.'
    )
    sent = send_user_email(user, subject, body)
    if sent:
        return True

    # Fallback: in DEBUG the code is exposed on the server console so local
    # development isn't blocked by a missing or revoked SMTP credential.
    # Production stays strict — without a delivered email we never hand out
    # a session.
    if getattr(settings, 'DEBUG', False):
        logger.warning(
            'SMTP delivery failed; login OTP for %s printed to console instead. '
            'Recipient: %s', user.username, email,
        )
        print('=' * 62)
        print(f'  [LOGIN OTP] {user.display_name} <{email}>')
        print(f'  One-time code : {otp}')
        print('=' * 62)
        request.session['dev_otp'] = {
            'code': otp,
            'expires': (timezone.now() + timedelta(minutes=10)).timestamp(),
        }
        return True

    firestore_db.delete_otp(user.pk)
    return False


def verify_otp_view(request):
    """Complete the sign-in by confirming the email One-Time PIN."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    pending_id = request.session.get('otp_user_id')
    form = OTPVerificationForm()
    if not pending_id:
        request.session.pop('dev_otp', None)
        messages.error(request, 'Your sign-in session has expired. Please log in again.')
        return redirect('login')

    user = get_user(pending_id)
    if user is None:
        request.session.pop('otp_user_id', None)
        request.session.pop('dev_otp', None)
        messages.error(request, 'Your sign-in session has expired. Please log in again.')
        return redirect('login')

    if request.method == 'POST':
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp_code']
            if firestore_db.verify_otp(user.pk, code):
                request.session.pop('otp_user_id', None)
                request.session.pop('dev_otp', None)
                login_user(request, user)
                log_activity(user, 'User Login', 'OTP verified, user logged in.', request)
                messages.success(request, f'Welcome back, {user.display_name}!')
                next_url = request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}
                ):
                    return redirect(next_url)
                return redirect('dashboard')
            remaining = firestore_db.get_pending_otp(user.pk)
            if remaining is None:
                request.session.pop('otp_user_id', None)
                request.session.pop('dev_otp', None)
                messages.error(
                    request,
                    'Too many invalid attempts. Please log in again to receive a new code.'
                )
                log_activity(user, 'Login OTP Blocked',
                             'Exceeded OTP attempts, pending login discarded.', request)
                return redirect('login')
            messages.error(request, 'That code is incorrect. Please try again.')
            form.add_error('otp_code', 'Invalid code. Check your email and try again.')

    dev_otp_code = None
    if getattr(settings, 'DEBUG', False):
        entry = request.session.get('dev_otp') or {}
        if entry.get('code') and entry.get('expires', 0) > timezone.now().timestamp():
            dev_otp_code = entry['code']
        else:
            request.session.pop('dev_otp', None)

    return render(request, 'brgy/verify_otp.html', {
        'form': form,
        'page_title': 'Enter Login Code',
        'mailto_email': (getattr(user, 'email', '') or '').strip(),
        'masked_email': _mask_email(getattr(user, 'email', '')),
        'dev_otp_code': dev_otp_code,
    })


def resend_otp_view(request):
    """Issue a fresh OTP for the pending sign-in and email it again."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('login')
    pending_id = request.session.get('otp_user_id')
    if not pending_id:
        messages.error(request, 'Your sign-in session has expired. Please log in again.')
        return redirect('login')
    user = get_user(pending_id)
    if user is None:
        request.session.pop('otp_user_id', None)
        messages.error(request, 'Your sign-in session has expired. Please log in again.')
        return redirect('login')
    if _send_login_otp(request, user):
        messages.success(request, 'A new code has been sent to your email.')
    else:
        messages.error(request, 'We could not send a new code. Please log in again.')
        request.session.pop('otp_user_id', None)
        request.session.pop('dev_otp', None)
        return redirect('login')
    return redirect('verify_otp')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = ResidentRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            # Notify staff of the new registration
            if user.barangay_id:
                for staff in staff_of_barangay(user.barangay_id):
                    notify(
                        staff['id'],
                        'New Resident Registration',
                        f'{user.display_name} has registered and awaits verification.',
                        link=reverse('verify_residents'),
                    )
            # Notify admins of the new registration
            notify_admins(
                'New Resident Registration',
                f'{user.display_name} has registered and awaits verification.',
                link=reverse('admin_dashboard'),
            )
            log_activity(user, 'Resident Registration', 'Resident registered an account.', request,
                     subject_user_id=user.pk)
            messages.success(
                request,
                'Registration successful! Your account is pending verification by barangay staff. '
                'You can log in to check your verification status.'
            )
            return redirect('login')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ResidentRegistrationForm()
    return render(request, 'brgy/register.html', {'form': form, 'page_title': 'Create Account'})


def logout_view(request):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('login')
    if request.user.is_authenticated:
        log_activity(request.user, 'User Logout', 'User logged out.', request)
    logout_user(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def dashboard_redirect(request):
    user = request.user
    if user.role == 'admin':
        return redirect('admin_dashboard')
    elif user.role == 'staff':
        return redirect('staff_dashboard')
    else:
        return redirect('resident_dashboard')


# ═══════════════════════════════════════════════════════════════
# RESIDENT VIEWS
# ═══════════════════════════════════════════════════════════════

@login_required
@role_required('resident')
def resident_dashboard(request):
    user = request.user
    if not user.is_verified_resident:
        return render(request, 'brgy/resident/dashboard.html', {
            'unverified': True,
            'page_title': 'Resident Dashboard',
            'rejection_reason': user.rejection_reason if user.verification_status == 'rejected' else '',
        })
    reqs = firestore_db.list_document_requests(
        filters=[('resident_id', '==', user.pk)],
        order_by='created_at',
        descending=True,
    )
    reqs = [DocumentRequest(r) for r in reqs]
    total = len(reqs)
    pending = sum(1 for r in reqs if r.status == 'pending')
    approved = sum(1 for r in reqs if r.status in ('approved', 'printed'))
    ready = sum(1 for r in reqs if r.status == 'ready_for_pickup')
    completed = sum(1 for r in reqs if r.status == 'completed')
    recent = reqs[:5]
    all_notifications = firestore_db.list_notifications(
        filters=[('user_id', '==', user.pk)],
        order_by='created_at',
        descending=True,
    )
    unread_updates = [
        Notification(n) for n in all_notifications
        if not n.get('is_read')
    ][:3]
    request.notifications_loaded = True
    latest_announcements = [
        Announcement(d) for d in firestore_db.list_announcements()
        if d.get('is_published') and d.get('published_at')
        and (d.get('barangay_id') is None or d.get('barangay_id') == user.barangay_id)
    ][:3]
    return render(request, 'brgy/resident/dashboard.html', {
        'unverified': False,
        'page_title': 'Resident Dashboard',
        'total': total,
        'pending': pending,
        'approved': approved,
        'ready': ready,
        'completed': completed,
        'recent_requests': recent,
        'unread_updates': unread_updates,
        'latest_announcements': latest_announcements,
        'recent_notifications': [Notification(n) for n in all_notifications[:5]],
        'unread_notification_count': sum(1 for n in all_notifications if not n.get('is_read')),
    })


@login_required
@role_required('resident')
def resident_profile(request):
    user = request.user
    if request.method == 'POST':
        if request.POST.get('edit_mode') == 'true':
            updates = {
                'first_name': request.POST.get('first_name', user.first_name),
                'middle_name': request.POST.get('middle_name', user.middle_name),
                'last_name': request.POST.get('last_name', user.last_name),
                'email': request.POST.get('email', user.email),
                'phone_number': request.POST.get('phone_number', user.phone_number),
                'occupation': request.POST.get('occupation', user.occupation),
                'address': request.POST.get('address', user.address),
            }
            birth_date = request.POST.get('birth_date')
            updates['birth_date'] = None
            if birth_date:
                try:
                    updates['birth_date'] = datetime.strptime(birth_date, '%Y-%m-%d').date()
                except ValueError:
                    pass

            gender = request.POST.get('gender')
            if gender:
                updates['gender'] = gender
            civil_status = request.POST.get('civil_status')
            if civil_status:
                updates['civil_status'] = civil_status
            id_type = request.POST.get('id_type')
            if id_type:
                updates['id_type'] = id_type

            # Validate the submitted profile fields before saving.
            try:
                for field in ('first_name', 'last_name'):
                    if not (updates.get(field) or '').strip():
                        raise ValidationError(f'{field.replace("_", " ").title()} is required.')
                email = (updates.get('email') or '').strip()
                if not email:
                    raise ValidationError('Email is required.')
                validate_email(email)
                phone = (updates.get('phone_number') or '').strip()
                if phone and not re.match(r'^[+]?[0-9\s\-()]{7,20}$', phone):
                    raise ValidationError('Phone number is not valid.')
                existing_email = firestore_db.get_user_by_email(email)
                if existing_email and existing_email.get('id') != user.pk:
                    raise ValidationError('An account with that email already exists.')
                if 'birth_date' in updates and updates['birth_date']:
                    if updates['birth_date'] > date.today():
                        raise ValidationError('Birth date cannot be in the future.')
            except ValidationError as e:
                messages.error(request, ' '.join(e.messages))
                return redirect('profile')

            try:
                if 'profile_picture' in request.FILES:
                    updates['profile_picture'] = _save_uploaded_file(
                        request.FILES['profile_picture'], 'profile_pictures',
                        IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'profile picture',
                    )
                if 'id_front' in request.FILES:
                    updates['id_front'] = _save_uploaded_file(
                        request.FILES['id_front'], 'resident_ids',
                        IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'ID image',
                    )
                if 'id_back' in request.FILES:
                    updates['id_back'] = _save_uploaded_file(
                        request.FILES['id_back'], 'resident_ids',
                        IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'ID image',
                    )
                if 'id_selfie' in request.FILES:
                    updates['id_selfie'] = _save_uploaded_file(
                        request.FILES['id_selfie'], 'resident_ids',
                        IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'ID selfie',
                    )
            except ValidationError as e:
                messages.error(request, ' '.join(e.messages))
                return redirect('profile')

            if 'id_front' in request.FILES or 'id_back' in request.FILES or 'id_selfie' in request.FILES:
                current = firestore_db.get_user(user.pk)
                if current and current.get('verification_status') == 'rejected':
                    updates['verification_status'] = 'pending'
                    updates['rejection_reason'] = ''

            firestore_db.update_user(user.pk, updates)
            data = firestore_db.get_user(user.pk)
            request.user = CustomUser(data)
            log_activity(request.user, 'Profile Updated', 'Profile updated.', request)
            messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    # Profile completion calculation
    check_fields = [
        user.first_name, user.last_name, user.email,
        user.phone_number, user.birth_date, user.gender,
        user.civil_status, user.occupation, user.address,
        user.profile_picture, user.id_front, user.id_back,
    ]
    filled = sum(1 for f in check_fields if f)
    profile_completion = round((filled / len(check_fields)) * 100)
    profile_completion_float = round(263.89 * (1 - profile_completion / 100), 2)

    recent_requests = [DocumentRequest(r) for r in firestore_db.list_document_requests(
        filters=[('resident_id', '==', user.pk)],
        order_by='created_at',
        descending=True,
    )[:5]]

    return render(request, 'brgy/resident/profile.html', {
        'page_title': 'My Profile',
        'profile_completion': profile_completion,
        'profile_completion_float': profile_completion_float,
        'recent_requests': recent_requests,
        'password_form': ChangePasswordForm(),
    })


@login_required
@role_required('resident')
def resident_password_change(request):
    user = request.user
    if request.method != 'POST':
        return redirect('profile')
    form = ChangePasswordForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please correct the errors below.')
        return redirect('profile')
    if not user.check_password(form.cleaned_data['current_password']):
        messages.error(request, 'Your current password is incorrect.')
        return redirect('profile')
    new_password = form.cleaned_data['new_password']
    firestore_db.update_user(user.pk, {'password': make_password(new_password)})
    data = firestore_db.get_user(user.pk)
    request.user = CustomUser(data)
    # Refresh the session auth hash so every other logged-in session is invalidated.
    from django.contrib.auth import HASH_SESSION_KEY
    request.session[HASH_SESSION_KEY] = request.user.get_session_auth_hash()
    log_activity(request.user, 'Password Changed', 'Password changed.', request)
    notify(request.user.pk, 'Password Changed', 'Your password has been updated.')
    messages.success(request, 'Your password has been updated successfully.')
    return redirect('profile')


@login_required
@role_required('resident')
def request_document(request):
    user = request.user
    if not user.is_verified_resident:
        messages.warning(request, 'Your account must be verified before you can request documents.')
        return redirect('resident_dashboard')
    doc_types = []
    for d in firestore_db.list_document_types(
        filters=[('is_active', '==', True)],
        order_by='name',
    ):
        dt = DocumentType(d)
        if not dt.is_active:
            continue
        if dt.is_global:
            override = get_override_for(dt.pk, user.barangay_id)
            if override is None:
                continue
            dt._data['fee'] = float(override.fee or 0)
            dt._data['has_template_effective'] = bool(override.has_template)
        elif dt.barangay_id != user.barangay_id:
            continue
        else:
            dt._data['fee'] = float(dt.fee if dt.fee is not None else 0)
            dt._data['has_template_effective'] = dt.has_template
        doc_types.append(dt)
    today = timezone.localdate()
    return render(request, 'brgy/resident/request_document.html', {
        'doc_types': doc_types,
        'today': today.isoformat(),
        'max_pickup': (today + timedelta(days=60)).isoformat(),
        'page_title': 'Request Documents',
    })


def _preview_image_handler(max_dim=1024):
    """Downscale embedded images in the preview HTML so it stays light.

    The printed .docx is unaffected (images are only re-encoded for the
    browser preview). Large/full-resolution scans would otherwise balloon the
    HTML into megabytes of base64 and freeze the resident preview modal.
    """
    def convert_image(image):
        import base64
        from io import BytesIO
        from PIL import Image as PilImage

        raw = None
        with image.open() as fh:
            raw = fh.read()
        mime = image.content_type or 'image/png'
        try:
            img = PilImage.open(BytesIO(raw))
            img.load()
            fmt = (img.format or 'PNG').upper()
            scale = min(1.0, max_dim / max(img.size))
            if scale < 1.0:
                img = img.resize(
                    (round(img.width * scale), round(img.height * scale)),
                    PilImage.LANCZOS,
                )
            use_jpeg = max(img.size) > 640
            if use_jpeg:
                fmt, mime = 'JPEG', 'image/jpeg'
                if img.mode in ('RGBA', 'LA', 'P'):
                    rgba = img.convert('RGBA') if img.mode != 'RGBA' else img
                    bg = PilImage.new('RGB', rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[-1])
                    img = bg
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
            out = BytesIO()
            img.save(out, format=fmt, optimize=True, quality=65)
            payload = out.getvalue()
        except Exception:
            payload = raw
            mime = image.content_type or 'image/png'
        return {
            'src': 'data:{0};base64,{1}'.format(
                mime, base64.b64encode(payload).decode('ascii')
            )
        }

    from mammoth.images import img_element
    return img_element(convert_image)


@login_required
@role_required('resident')
def document_preview(request, pk):
    user = request.user
    try:
        doc_type = DocumentType(firestore_db.get_document_type(pk))
    except Exception:
        return JsonResponse({'error': 'Document type not found.'}, status=404)

    if not doc_type or not doc_type.is_active:
        return JsonResponse({'error': 'Document type not found.'}, status=404)

    template_path = None
    if doc_type.is_global:
        barangay = user.barangay
        override = get_override_for(doc_type.pk, barangay.pk if barangay else None)
        if override and override.has_template:
            template_path = override.template_file.path
    else:
        if doc_type.has_template:
            template_path = doc_type.template_file.path

    if not template_path or not os.path.exists(template_path):
        return JsonResponse({'error': 'No template available.'}, status=404)

    barangay = user.barangay
    sample_verify_url = _absolute_url(
        request, reverse('verify_document') + '?code=XXXXXXXXXXXX'
    )
    namespace = _build_template_context(
        resident=user, barangay=barangay, doc_type=doc_type,
        purpose='N/A', request_number='BRG-XXXXXXXX-XXXX',
        verification_code='XXXXXXXXXXXX', verify_url=sample_verify_url,
    )
    if doc_type.is_global:
        override = get_override_for(doc_type.pk, barangay.pk if barangay else None)
        variables = _template_detected_variables(doc_type, override)
    else:
        variables = _template_detected_variables(doc_type)
    token_salt = _doc_template_salt(doc_type)
    if variables is None:
        variables = _live_template_variables(template_path, token_salt)
    context = _resolve_template_context(namespace, variables, token_salt=token_salt)
    _inject_token_values(
        context, namespace, doc_type,
        override if doc_type.is_global else None,
    )

    doc = DocxTemplate(template_path)
    doc.render(context)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    result = mammoth.convert_to_html(
        file_stream, convert_image=_preview_image_handler()
    )
    html = result.value

    return JsonResponse({
        'html': html,
        'doc_name': doc_type.name,
    })


@login_required
@role_required('resident')
def submit_bulk_request(request):
    user = request.user
    if not user.is_verified_resident:
        messages.warning(request, 'Your account must be verified before you can request documents.')
        return redirect('resident_dashboard')

    if request.method == 'POST':
        doc_ids = []
        for doc_id in request.POST.getlist('document_type[]'):
            if doc_id and doc_id not in doc_ids:
                doc_ids.append(doc_id)
        quantities = request.POST.getlist('quantity[]')
        purpose = (request.POST.get('purpose') or '').strip()
        contact_number = (request.POST.get('contact_number') or user.phone_number or '').strip()
        pickup_date = request.POST.get('pickup_date', '')

        if not doc_ids:
            messages.error(request, 'Please add at least one document to your request.')
            return redirect('request_document')

        if not purpose:
            messages.error(request, 'Please provide a purpose for your request.')
            return redirect('request_document')

        if len(purpose) > 500:
            messages.error(request, 'Purpose is too long (max 500 characters).')
            return redirect('request_document')

        if not re.match(r'^\+?[0-9]{10,15}$', contact_number):
            messages.error(request, 'Please enter a valid contact number (e.g. 09171234567).')
            return redirect('request_document')

        today = timezone.localdate()
        parsed_pickup = None
        if pickup_date:
            try:
                parsed_pickup = datetime.strptime(pickup_date, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Invalid pickup date.')
                return redirect('request_document')
            if parsed_pickup < today:
                messages.error(request, 'Pickup date cannot be in the past.')
                return redirect('request_document')
            if parsed_pickup > today + timedelta(days=60):
                messages.error(request, 'Pickup date cannot be more than 60 days from today.')
                return redirect('request_document')

        # Build line items with authoritative fee snapshot from the document type,
        # validating each doc against the resident's barangay.
        items = {}
        for i, doc_id in enumerate(doc_ids):
            doc_type = _doc_type_or_404(doc_id)
            if doc_type.is_global:
                override = get_override_for(doc_type.pk, user.barangay_id)
                if override is None:
                    raise Http404
                fee_per_unit = float(override.fee or 0)
            else:
                if doc_type.barangay_id != user.barangay_id:
                    raise Http404
                fee_per_unit = float(doc_type.fee if doc_type.fee is not None else 0)
            try:
                qty = int(quantities[i]) if i < len(quantities) else 1
            except (ValueError, TypeError):
                qty = 1
            qty = max(1, min(qty, 20))
            items[doc_id] = {
                'doc_type': doc_type,
                'qty': qty,
                'fee_per_unit': fee_per_unit,
            }

        requirement_files = {}
        for doc_id, item in items.items():
            files = []
            for uploaded in request.FILES.getlist(f'requirements_{doc_id}'):
                try:
                    files.append(_save_uploaded_file(
                        uploaded, 'requirement_files',
                        REQUIREMENT_EXTENSIONS, MAX_REQUIREMENT_FILE_SIZE,
                        'requirement file',
                    ))
                except ValidationError as e:
                    messages.error(request, ' '.join(e.messages))
                    return redirect('request_document')
            requirement_files[doc_id] = files

        request_data = {
            'resident_id': user.pk,
            'request_number': firestore_db.next_request_number(),
            # Cryptographically secure random for the public verification code.
            'verification_code': _make_verification_code(),
            'purpose': purpose,
            'contact_number': contact_number,
            'pickup_date': parsed_pickup,
            'status': 'pending',
            'staff_notes': '',
            'rejection_reason': '',
            'processed_by_id': None,
            'completed_at': None,
            'approved_at': None,
            'printed_at': None,
            'ready_at': None,
        }
        request_id = firestore_db.create_document_request(request_data)

        for doc_id, item in items.items():
            firestore_db.create_document_request_item({
                'request_id': request_id,
                'document_type_id': item['doc_type'].pk,
                'quantity': item['qty'],
                'fee_per_unit': item['fee_per_unit'],
                'requirement_files': requirement_files.get(doc_id, []),
            })

        request_data['id'] = request_id
        doc_req = DocumentRequest(request_data)

        # Notify staff
        if user.barangay_id:
            for staff in staff_of_barangay(user.barangay_id):
                notify(
                    staff['id'],
                    'New Document Request',
                    f'{user.display_name} submitted a new document request ({doc_req.request_number}).',
                    link='/staff/requests/',
                )
        # Notify resident
        notify(
            user.pk,
            'Request Submitted',
            f'Your document request has been submitted. Request #: {doc_req.request_number}',
            link=reverse('request_history'),
        )
        log_activity(user, 'Document Request Submitted',
                     f'Submitted document request {doc_req.request_number}. Requested: '
                     + ', '.join(
                         f"{item['doc_type'].name} x{item['qty']}"
                         for item in items.values()
                     ) + '.', request)

        messages.success(
            request,
            f'Your document request has been submitted successfully! Request #: {doc_req.request_number}'
        )
        return redirect('request_history')

    return redirect('request_document')


@login_required
@role_required('resident')
def request_history(request):
    user = request.user
    if not user.is_verified_resident:
        return redirect('resident_dashboard')
    reqs = firestore_db.list_document_requests(
        filters=[('resident_id', '==', user.pk)],
        order_by='created_at',
        descending=True,
    )
    reqs = [DocumentRequest(r) for r in reqs]
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    if status_filter:
        reqs = [r for r in reqs if r.status == status_filter]
    if search:
        search = search.lower()
        reqs = [r for r in reqs if search in _request_search_text(r)]
    paginator = Paginator(reqs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/resident/request_history.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
        'status_choices': DocumentRequest.Status.choices,
        'page_title': 'Request History',
    })


@login_required
@role_required('resident', 'admin')
def notifications_view(request):
    notifications = firestore_db.list_notifications(
        filters=[('user_id', '==', request.user.pk)],
        order_by='created_at',
        descending=True,
    )
    notifications = [Notification(n) for n in notifications]
    unread_count = sum(1 for n in notifications if not n.is_read)
    paginator = Paginator(notifications, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/resident/notifications.html', {'page_obj': page_obj, 'page_title': 'Notifications', 'unread_count': unread_count})


@login_required
@role_required('staff')
def staff_notifications(request):
    notifications = firestore_db.list_notifications(
        filters=[('user_id', '==', request.user.pk)],
        order_by='created_at',
        descending=True,
    )
    notifications = [Notification(n) for n in notifications]
    unread_count = sum(1 for n in notifications if not n.is_read)
    paginator = Paginator(notifications, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/resident/notifications.html', {'page_obj': page_obj, 'page_title': 'Notifications', 'unread_count': unread_count})


@login_required
def mark_notification_read(request, pk):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect(notifications_url_name(request.user))
    data = firestore_db.get_notification(pk)
    if not data or data.get('user_id') != request.user.pk:
        raise Http404
    firestore_db.update_notification(pk, {'is_read': True})
    link = data.get('link') or ''
    if link and url_has_allowed_host_and_scheme(link, allowed_hosts={request.get_host()}):
        return redirect(link)
    return redirect(notifications_url_name(request.user))


@login_required
@role_required('resident', 'staff', 'admin')
def set_notification_read(request, pk):
    """Mark a notification read or unread (3-dot menu). POST ``read=1|0``."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect(notifications_url_name(request.user))
    data = firestore_db.get_notification(pk)
    if not data or data.get('user_id') != request.user.pk:
        raise Http404
    is_read = request.POST.get('read') in ('1', 'true', 'True', 'on', 'yes')
    firestore_db.update_notification(pk, {'is_read': is_read})
    return redirect(notifications_url_name(request.user))


@login_required
@role_required('resident', 'staff', 'admin')
def delete_notification(request, pk):
    """Permanently remove a notification (3-dot menu). POST only."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect(notifications_url_name(request.user))
    data = firestore_db.get_notification(pk)
    if not data or data.get('user_id') != request.user.pk:
        raise Http404
    firestore_db.delete_notification(pk)
    return redirect(notifications_url_name(request.user))


@login_required
def unread_notification_count(request):
    notifications = firestore_db.list_notifications(
        filters=[('user_id', '==', request.user.pk)],
        order_by='created_at',
        descending=True,
    )
    return JsonResponse({'count': sum(1 for n in notifications if not n.get('is_read'))})


@login_required
def mark_all_notifications_read(request):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect(notifications_url_name(request.user))
    notifications = firestore_db.list_notifications(
        filters=[('user_id', '==', request.user.pk), ('is_read', '==', False)]
    )
    for notif in notifications:
        firestore_db.update_notification(notif['id'], {'is_read': True})
    messages.success(request, 'All notifications marked as read.')
    return redirect(notifications_url_name(request.user))


@login_required
@role_required('resident')
def cancel_request(request, pk):
    doc_req = _request_or_404(pk)
    if doc_req.resident_id != request.user.pk:
        raise Http404

    if doc_req.status == 'pending':
        if doc_req.resident and doc_req.resident.barangay_id:
            for staff in staff_of_barangay(doc_req.resident.barangay_id):
                notify(
                    staff['id'],
                    'Request Cancelled',
                    f'{doc_req.resident.display_name} cancelled their document request '
                    f'({doc_req.request_number}).',
                    link=reverse('staff_requests'),
                )
        new_display = _apply_status_transition(
            doc_req, 'cancelled', request.user, request=request,
        )
        log_activity(request.user, 'Request Cancelled',
                     f'Cancelled request {doc_req.request_number}.', request,
                     subject_user_id=doc_req.resident_id)
        if new_display:
            messages.success(
                request,
                f'Request {doc_req.request_number} has been successfully cancelled.'
            )
        else:
            messages.info(request, 'That request is already cancelled.')
    else:
        messages.error(request, 'You can only cancel pending requests.')

    return redirect('request_history')


@login_required
@role_required('resident')
def track_request(request, pk, item_pk=None):
    doc_req = _request_or_404(pk)
    if doc_req.resident_id != request.user.pk:
        raise Http404

    items = list(doc_req.items.all())
    status_colors = {
        'rejected': 'danger',
        'completed': 'primary',
        'ready_for_pickup': 'success',
        'printed': 'info',
        'approved': 'info',
        'pending': 'warning',
    }
    item_statuses = [
        {
            'item': item,
            'status': _item_status(item, doc_req),
            'color': status_colors.get(_item_status(item, doc_req), 'muted'),
        }
        for item in items
    ]

    selected_item = None
    if item_pk:
        selected_item = next((i for i in items if i.pk == str(item_pk)), None)
        if selected_item is None:
            raise Http404

    printed_at = None
    if selected_item:
        item_status = _item_status(selected_item, doc_req)
        if item_status == 'printed' and selected_item.printed_at:
            printed_at = selected_item.printed_at
    if printed_at is None:
        printed_at = doc_req.printed_at

    if doc_req.status == 'rejected':
        display_status = 'rejected'
    elif doc_req.status == 'cancelled':
        display_status = 'cancelled'
    elif selected_item:
        display_status = _item_status(selected_item, doc_req)
    else:
        display_status = doc_req.status

    progress_map = {
        'rejected': (100, 'danger'),
        'cancelled': (100, 'muted'),
        'pending': (25, 'warning'),
        'approved': (50, 'info'),
        'printed': (60, 'info'),
        'ready_for_pickup': (75, 'success'),
        'completed': (100, 'primary'),
    }
    progress_percent, progress_color = progress_map.get(display_status, (0, 'muted'))
    progress = {
        'percent': progress_percent,
        'color': progress_color,
        'offset': round(326.73 * (1 - progress_percent / 100.0), 2),
    }

    reach_map = {
        'pending': 1,
        'approved': 2,
        'printed': 3,
        'ready_for_pickup': 4,
        'completed': 5,
    }
    step_configs = [
        ('submitted', 'Submitted', 'fa-paper-plane', doc_req.created_at),
        ('approved', 'Approved', 'fa-check', doc_req.approved_at),
        ('printed', 'Printed', 'fa-print', printed_at),
        ('ready_for_pickup', 'Ready for Pickup', 'fa-box-open', doc_req.ready_at),
        ('completed', 'Completed', 'fa-flag-checkered', doc_req.completed_at),
    ]
    reached = reach_map.get(display_status)
    steps = []
    if display_status != 'rejected' and reached is not None:
        for i, (key, label, icon, date) in enumerate(step_configs):
            if i < reached:
                state = 'done'
            elif i == reached:
                state = 'active'
            else:
                state = 'todo'
            steps.append({'key': key, 'label': label, 'icon': icon, 'state': state, 'date': date})

    total_fee = sum(item.total_fee for item in items)

    return render(request, 'brgy/resident/track_request.html', {
        'req': doc_req,
        'item_statuses': item_statuses,
        'selected_item': selected_item,
        'printed_at': printed_at,
        'display_status': display_status,
        'progress': progress,
        'steps': steps,
        'total_fee': total_fee,
        'page_title': f'Track Request - {doc_req.request_number}',
    })


def _item_status(item, doc_req):
    """Compute the per-document status for a single request item.

    When the whole request is rejected/completed/ready, every document inherits
    that terminal state. Otherwise a document is only as far along as it has
    actually been printed.
    """
    req_status = doc_req.status
    if req_status == 'rejected':
        return 'rejected'
    if req_status == 'completed':
        return 'completed'
    if req_status == 'ready_for_pickup':
        return 'ready_for_pickup'
    if item.is_printed or (req_status == 'printed' and doc_req.printed_at):
        return 'printed'
    if req_status == 'approved' or req_status == 'printed':
        return 'approved'
    return 'pending'


# ═══════════════════════════════════════════════════════════════
# STAFF VIEWS
# ═══════════════════════════════════════════════════════════════

@login_required
@role_required('staff')
def staff_dashboard(request):
    user = request.user
    brgy = user.barangay
    all_users = firestore_db.list_users()
    residents = [
        u for u in all_users
        if u.get('role') == 'resident' and u.get('barangay_id') == brgy.pk
    ]
    pending_verifications = len([u for u in residents if u.get('verification_status') == 'pending'])
    verified_residents = len([u for u in residents if u.get('verification_status') == 'approved'])

    doc_requests = requests_for_barangay(brgy.pk)
    pending_requests = sum(1 for r in doc_requests if r.status == 'pending')
    approved_requests = sum(1 for r in doc_requests if r.status in ('approved', 'printed'))
    ready_requests = sum(1 for r in doc_requests if r.status == 'ready_for_pickup')
    completed_requests = sum(1 for r in doc_requests if r.status == 'completed')
    total_requests = len(doc_requests)
    today = timezone.localdate()
    today_requests = sum(
        1 for r in doc_requests
        if r.created_at is not None and r.created_at.date() == today
    )
    today_completed = sum(
        1 for r in doc_requests
        if r.completed_at and r.completed_at.date() == today
    )
    pending_residents = [CustomUser(u) for u in residents if u.get('verification_status') == 'pending'][:5]
    pending_doc_requests = [r for r in doc_requests if r.status == 'pending'][:5]

    residents_by_id = {u.get('id'): u for u in all_users}
    doc_types = {d.get('id'): d for d in firestore_db.list_document_types()}

    for req in pending_doc_requests:
        resident_data = residents_by_id.get(req.resident_id)
        object.__setattr__(req, 'resident_name', CustomUser(resident_data).display_name if resident_data else 'Unknown Resident')
        item_previews = []
        for item in get_request_items(req.pk):
            doc_name = 'Document'
            dt = item._data.get('document_type_id')
            if dt and doc_types.get(dt):
                doc_name = doc_types[dt].get('name') or 'Document'
            quantity = item.quantity
            item_previews.append(f'{doc_name}{" ×%d" % quantity if quantity and quantity > 1 else ""}')
        object.__setattr__(req, 'items_preview', ', '.join(item_previews))

    return render(request, 'brgy/staff/dashboard.html', {
        'page_title': 'Staff Dashboard',
        'pending_verifications': pending_verifications,
        'verified_residents': verified_residents,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'ready_requests': ready_requests,
        'completed_requests': completed_requests,
        'total_requests': total_requests,
        'today_requests': today_requests,
        'today_completed': today_completed,
        'pending_residents': pending_residents,
        'pending_doc_requests': pending_doc_requests,
    })


@login_required
@role_required('staff')
def staff_profile(request):
    user = request.user
    info_form = StaffProfileForm(instance=user)
    password_form = ChangePasswordForm()

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'info')

        if form_type == 'password':
            password_form = ChangePasswordForm(request.POST)
            if password_form.is_valid():
                if not user.check_password(password_form.cleaned_data['current_password']):
                    messages.error(request, 'Your current password is incorrect.')
                else:
                    new_password = password_form.cleaned_data['new_password']
                    firestore_db.update_user(user.pk, {
                        'password': make_password(new_password),
                    })
                    data = firestore_db.get_user(user.pk)
                    request.user = CustomUser(data)
                    from django.contrib.auth import HASH_SESSION_KEY
                    request.session[HASH_SESSION_KEY] = request.user.get_session_auth_hash()
                    log_activity(request.user, 'Password Changed', 'Password changed.', request)
                    messages.success(request, 'Your password has been updated successfully.')
                    return redirect('staff_profile')
            return render(request, 'brgy/staff/profile.html', {
                'info_form': info_form,
                'password_form': password_form,
                'page_title': 'My Profile',
            })

        info_form = StaffProfileForm(request.POST, instance=user)
        if info_form.is_valid():
            updates = {
                'first_name': info_form.cleaned_data['first_name'],
                'last_name': info_form.cleaned_data['last_name'],
                'email': info_form.cleaned_data['email'],
                'phone_number': info_form.cleaned_data.get('phone_number', ''),
            }
            try:
                if 'profile_picture' in request.FILES:
                    updates['profile_picture'] = _save_uploaded_file(
                        request.FILES['profile_picture'], 'profile_pictures',
                        IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'profile picture',
                    )
            except ValidationError as e:
                messages.error(request, ' '.join(e.messages))
                return redirect('staff_profile')
            firestore_db.update_user(user.pk, updates)
            data = firestore_db.get_user(user.pk)
            request.user = CustomUser(data)
            log_activity(request.user, 'Profile Updated', 'Profile updated.', request)
            messages.success(request, 'Profile updated successfully!')
            return redirect('staff_profile')
        password_form = ChangePasswordForm()

    return render(request, 'brgy/staff/profile.html', {
        'info_form': info_form,
        'password_form': password_form,
        'page_title': 'My Profile',
    })


@login_required
@role_required('admin')
def admin_profile(request):
    user = request.user
    info_form = StaffProfileForm(instance=user)
    password_form = ChangePasswordForm()

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'info')

        if form_type == 'password':
            password_form = ChangePasswordForm(request.POST)
            if password_form.is_valid():
                if not user.check_password(password_form.cleaned_data['current_password']):
                    messages.error(request, 'Your current password is incorrect.')
                else:
                    new_password = password_form.cleaned_data['new_password']
                    firestore_db.update_user(user.pk, {
                        'password': make_password(new_password),
                    })
                    data = firestore_db.get_user(user.pk)
                    request.user = CustomUser(data)
                    from django.contrib.auth import HASH_SESSION_KEY
                    request.session[HASH_SESSION_KEY] = request.user.get_session_auth_hash()
                    log_activity(request.user, 'Password Changed', 'Password changed.', request)
                    messages.success(request, 'Your password has been updated successfully.')
                    return redirect('admin_profile')
            return render(request, 'brgy/admin/profile.html', {
                'info_form': info_form,
                'password_form': password_form,
                'page_title': 'My Profile',
            })

        info_form = StaffProfileForm(request.POST, instance=user)
        if info_form.is_valid():
            updates = {
                'first_name': info_form.cleaned_data['first_name'],
                'last_name': info_form.cleaned_data['last_name'],
                'email': info_form.cleaned_data['email'],
                'phone_number': info_form.cleaned_data.get('phone_number', ''),
            }
            try:
                if 'profile_picture' in request.FILES:
                    updates['profile_picture'] = _save_uploaded_file(
                        request.FILES['profile_picture'], 'profile_pictures',
                        IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'profile picture',
                    )
            except ValidationError as e:
                messages.error(request, ' '.join(e.messages))
                return redirect('admin_profile')
            firestore_db.update_user(user.pk, updates)
            data = firestore_db.get_user(user.pk)
            request.user = CustomUser(data)
            log_activity(request.user, 'Profile Updated', 'Profile updated.', request)
            messages.success(request, 'Profile updated successfully!')
            return redirect('admin_profile')
        password_form = ChangePasswordForm()

    return render(request, 'brgy/admin/profile.html', {
        'info_form': info_form,
        'password_form': password_form,
        'page_title': 'My Profile',
    })


@login_required
@role_required('staff')
def verify_residents(request):
    user = request.user
    status_filter = request.GET.get('status', '')
    if status_filter == 'all':
        status_filter = ''
    search = request.GET.get('search', '')

    all_users = firestore_db.list_users(
        order_by='date_joined', descending=True,
    )
    residents = [
        CustomUser(u) for u in all_users
        if u.get('role') == 'resident' and u.get('barangay_id') == user.barangay_id
    ]
    status_counts = {'pending': 0, 'approved': 0, 'rejected': 0}
    for r in residents:
        s = r.verification_status
        if s in status_counts:
            status_counts[s] += 1
    if status_filter:
        residents = [r for r in residents if r.verification_status == status_filter]
    if search:
        search = search.lower()
        residents = [
            r for r in residents
            if search in (r.first_name or '').lower()
            or search in (r.last_name or '').lower()
            or search in (r.username or '').lower()
            or search in (r.email or '').lower()
        ]
    paginator = Paginator(residents, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/staff/verify_residents.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
        'status_counts': status_counts,
        'page_title': 'Verify Residents',
    })


@login_required
@role_required('staff')
def approve_resident(request, pk):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('verify_residents')
    resident = _user_or_404(pk)
    if resident.role != 'resident' or resident.barangay_id != request.user.barangay_id:
        raise Http404
    firestore_db.update_user(resident.pk, {
        'verification_status': 'approved',
        'rejection_reason': '',
    })
    notify(
        resident.pk,
        'Account Verified',
        'Your account has been verified. You can now request barangay documents.',
        link=reverse('resident_dashboard'),
    )
    send_user_email(
        resident,
        'Your barangay account is verified',
        'Your account has been verified. You can now request barangay documents '
        'online at the Barangay Document System.\n\n'
        f'Sign in here: {_absolute_url(request, "/login/")}',
    )
    log_activity(request.user, 'Resident Verified', 'Approved resident.', request,
                     subject_user_id=resident.pk)
    messages.success(request, f'{resident.display_name} has been verified.')
    return redirect('verify_residents')


@login_required
@role_required('staff')
def reject_resident(request, pk):
    resident = _user_or_404(pk)
    if resident.role != 'resident' or resident.barangay_id != request.user.barangay_id:
        raise Http404
    if request.method == 'POST':
        form = RejectForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']
            firestore_db.update_user(resident.pk, {
                'verification_status': 'rejected',
                'rejection_reason': reason,
            })
            notify(
                resident.pk,
                'Account Rejected',
                f'Your account verification was rejected. Reason: {reason}',
                link=reverse('resident_dashboard'),
            )
            send_user_email(
                resident,
                'Your barangay account verification was rejected',
                f'Your account verification was rejected.\n\nReason: {reason}\n\n'
                'If you would like to try again, sign in and update your details '
                f'here: {_absolute_url(request, "/login/")}',
            )
            log_activity(request.user, 'Resident Rejected', 'Rejected resident.', request,
                         subject_user_id=resident.pk)
            messages.success(request, f'{resident.display_name} has been rejected.')
            return redirect('verify_residents')
    else:
        form = RejectForm()
    return render(request, 'brgy/staff/reject_resident.html', {'resident': resident, 'form': form, 'page_title': 'Reject Resident'})


@login_required
@role_required('staff')
def toggle_resident_active(request, pk):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('verify_residents')
    resident = _user_or_404(pk)
    if resident.role != 'resident' or resident.barangay_id != request.user.barangay_id:
        raise Http404
    if resident.verification_status != 'approved':
        messages.error(request, 'Only verified residents can be deactivated.')
        return redirect('verify_residents')
    new_active = not resident.is_active
    firestore_db.update_user(resident.pk, {'is_active': new_active})
    if new_active:
        notify(
            resident.pk,
            'Account Reactivated',
            'Your account has been reactivated. You can log in and request barangay documents again.',
            link=reverse('resident_dashboard'),
        )
        log_activity(request.user, 'Resident Reactivated', 'Reactivated resident account.', request,
                     subject_user_id=resident.pk)
        messages.success(request, f'{resident.display_name} has been reactivated.')
    else:
        notify(
            resident.pk,
            'Account Deactivated',
            'Your account has been deactivated. Please contact your barangay office for assistance.',
            link=reverse('login'),
        )
        log_activity(request.user, 'Resident Deactivated', 'Deactivated resident account.', request,
                     subject_user_id=resident.pk)
        messages.success(request, f'{resident.display_name} has been deactivated.')
    next_url = request.GET.get('next') or ''
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('verify_residents')


@login_required
@role_required('staff', 'admin')
def manage_announcements(request):
    user = request.user
    announcements = []
    system_announcements = []
    for d in firestore_db.list_announcements():
        a = Announcement(d)
        if user.role == 'admin':
            announcements.append(a)
        elif d.get('barangay_id') == user.barangay_id:
            announcements.append(a)
        elif d.get('barangay_id') is None:
            system_announcements.append(a)
    announcements.sort(
        key=lambda a: a.published_at or a.created_at or firestore_db.utcnow(),
        reverse=True,
    )

    form = AnnouncementForm(request.POST or None, user=user)
    if request.method == 'POST' and form.is_valid():
        scope = form.cleaned_data.get('scope') or 'barangay'
        barangay_id = None
        if scope == 'barangay':
            barangay_id = form.cleaned_data.get('barangay') or user.barangay_id
        is_published = bool(form.cleaned_data.get('is_published'))
        firestore_db.create_announcement({
            'title': form.cleaned_data['title'],
            'body': form.cleaned_data['body'],
            'author_id': user.pk,
            'barangay_id': barangay_id,
            'is_published': is_published,
            'published_at': firestore_db.utcnow() if is_published else None,
        })
        log_activity(user, 'Announcement Created',
                     f'Announcement "{form.cleaned_data["title"]}" created.', request)
        messages.success(request, 'Announcement created.')
        return redirect('manage_announcements')

    return render(request, 'brgy/staff/manage_announcements.html', {
        'page_title': 'Manage Announcements',
        'announcements': announcements,
        'system_announcements': system_announcements,
        'form': form,
    })


@login_required
@role_required('staff', 'admin')
def toggle_announcement(request, pk):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('manage_announcements')
    announcement = get_announcement(pk)
    if announcement is None:
        raise Http404
    if request.user.role != 'admin' and announcement._data.get('barangay_id') != request.user.barangay_id:
        raise Http404
    new_published = not announcement.is_published
    firestore_db.update_announcement(pk, {
        'is_published': new_published,
        'published_at': firestore_db.utcnow() if new_published else None,
    })
    log_activity(request.user,
                 'Announcement Published' if new_published else 'Announcement Unpublished',
                 f'Announcement "{announcement.title}" {"published" if new_published else "unpublished"}.', request)
    messages.success(request, f'Announcement {"published" if new_published else "unpublished"} successfully.')
    return redirect('manage_announcements')


@login_required
@role_required('staff', 'admin')
def delete_announcement(request, pk):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('manage_announcements')
    announcement = get_announcement(pk)
    if announcement is None:
        raise Http404
    if request.user.role != 'admin' and announcement._data.get('barangay_id') != request.user.barangay_id:
        raise Http404
    firestore_db.delete_announcement(pk)
    log_activity(request.user, 'Announcement Deleted',
                 f'Announcement "{announcement.title}" deleted.', request)
    messages.success(request, 'Announcement deleted.')
    return redirect('manage_announcements')


@login_required
@role_required('staff')
def manage_requests(request):
    user = request.user
    doc_requests = requests_for_barangay(user.barangay_id)
    status_counts = {}
    for r in doc_requests:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    total_requests = len(doc_requests)
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if status_filter:
        doc_requests = [r for r in doc_requests if r.status == status_filter]
    if search:
        search = search.lower()
        doc_requests = [r for r in doc_requests if search in _request_search_text(r)]
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            doc_requests = [
                r for r in doc_requests
                if r.created_at is not None and r.created_at.date() >= from_date
            ]
        except ValueError:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            doc_requests = [
                r for r in doc_requests
                if r.created_at is not None and r.created_at.date() <= to_date
            ]
        except ValueError:
            pass
    paginator = Paginator(doc_requests, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    status_summary = [
        {'value': v, 'label': l, 'count': status_counts.get(v, 0)}
        for v, l in DocumentRequest.Status.choices
    ]
    return render(request, 'brgy/staff/manage_requests.html', {
        'page_obj': page_obj,
        'page_title': 'Document Requests',
        'status_filter': status_filter,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'status_counts': status_counts,
        'status_summary': status_summary,
        'total_requests': total_requests,
    })


@login_required
@role_required('staff')
def update_request_status(request, pk):
    doc_request = _request_or_404(pk)
    if not doc_request.barangay or doc_request.barangay.pk != request.user.barangay_id:
        raise Http404
    choices = _status_choices_for(doc_request.status)
    if not doc_request.is_paid:
        choices = [c for c in choices if c[0] != 'completed']
    if not choices:
        messages.info(
            request,
            f'Request {doc_request.request_number} is {doc_request.get_status_display()}; no further updates are available.'
        )
        return redirect('manage_requests')
    if request.method == 'POST':
        form = UpdateStatusForm(request.POST, choices=choices)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            notes = form.cleaned_data.get('staff_notes', '')
            rejection_reason = form.cleaned_data.get('rejection_reason', '')
            if new_status == 'completed' and not doc_request.is_paid:
                messages.error(
                    request,
                    'Payment must be recorded before this request can be completed.'
                )
                return redirect('update_request_status', pk=doc_request.pk)
            if new_status not in [c for c, _ in choices]:
                messages.error(request, 'That status transition is not allowed.')
                return redirect('update_request_status', pk=doc_request.pk)
            new_display = _apply_status_transition(
                doc_request, new_status, request.user,
                request=request, notes=notes, rejection_reason=rejection_reason,
            )
            if new_display:
                messages.success(
                    request,
                    f'Request {doc_request.request_number} is now {new_display}.'
                )
            else:
                messages.info(
                    request,
                    f'Request {doc_request.request_number} is already {doc_request.get_status_display()}.'
                )
            return redirect('manage_requests')
    else:
        form = UpdateStatusForm(choices=choices)
    total_fee = sum(item.total_fee for item in doc_request.items.all())
    payment_form = MarkPaymentForm()
    return render(request, 'brgy/staff/update_request.html', {
        'doc_request': doc_request, 'form': form, 'total_fee': total_fee,
        'payment_form': payment_form,
        'can_pay': doc_request.status in PAYABLE_STATUSES and not doc_request.is_paid,
        'page_title': f'Update Request - {doc_request.request_number}',
    })


@login_required
@role_required('staff')
def mark_ready_for_pickup(request, pk):
    doc_request = _request_or_404(pk)
    if not doc_request.barangay or doc_request.barangay.pk != request.user.barangay_id:
        raise Http404
    if request.method == 'POST':
        if doc_request.status != 'printed':
            messages.error(
                request,
                'This request must be printed before it can be marked ready for pickup.'
            )
            return redirect('manage_requests')
        pickup_date = request.POST.get('pickup_date', '')
        pickup_slot = request.POST.get('pickup_slot', '')
        parsed_pickup = None
        if pickup_date:
            try:
                parsed_pickup = datetime.strptime(pickup_date, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Invalid pickup date.')
                return redirect('manage_requests')
            if parsed_pickup < timezone.localdate():
                messages.error(request, 'Pickup date cannot be in the past.')
                return redirect('manage_requests')
            if parsed_pickup > timezone.localdate() + timedelta(days=60):
                messages.error(request, 'Pickup date cannot be more than 60 days from today.')
                return redirect('manage_requests')
        if pickup_slot not in dict(DocumentRequest.PickupSlot.choices):
            pickup_slot = 'morning'
        new_display = _apply_status_transition(
            doc_request, 'ready_for_pickup', request.user, request=request,
            pickup_date=parsed_pickup, pickup_slot=pickup_slot,
        )
        if new_display:
            messages.success(
                request,
                f'Request {doc_request.request_number} is now {new_display}.'
            )
        else:
            messages.info(
                request,
                f'Request {doc_request.request_number} is already {doc_request.get_status_display()}.'
            )
    else:
        messages.error(request, 'Invalid request.')
    return redirect('manage_requests')


# Statuses for which payment collection is allowed (post-approval).
PAYABLE_STATUSES = ('approved', 'printed', 'ready_for_pickup', 'completed')


@login_required
@role_required('staff')
def mark_paid(request, pk):
    doc_request = _request_or_404(pk)
    if not doc_request.barangay or doc_request.barangay.pk != request.user.barangay_id:
        raise Http404
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('manage_requests')

    payment_action = request.POST.get('payment_action', 'paid')

    # ── Mark as UNPAID ──────────────────────────────────────────
    if payment_action == 'unpaid':
        if not doc_request.is_paid:
            messages.info(request, 'This request is not marked as paid.')
            return redirect('manage_requests')
        firestore_db.update_document_request(doc_request.pk, {
            'payment_status': 'unpaid',
            'paid_at': None,
            'payment_method': '',
            'or_number': '',
        })
        notify(
            doc_request.resident_id,
            'Payment Status Updated',
            f'Payment on request {doc_request.request_number} has been marked as unpaid by the barangay office. Please contact your barangay for details.',
            link=reverse('request_history'),
        )
        log_activity(request.user, 'Payment Reverted',
                     f'Payment record cleared for {doc_request.request_number}.', request,
                     subject_user_id=doc_request.resident_id)
        messages.success(request, f'Payment for {doc_request.request_number} marked as unpaid.')
        return redirect('manage_requests')

    # ── Mark as PAID ────────────────────────────────────────────
    if doc_request.status not in PAYABLE_STATUSES:
        messages.error(request, 'This request is not eligible for payment collection yet.')
        return redirect('manage_requests')
    if doc_request.is_paid:
        messages.info(request, 'This request is already marked as paid.')
        return redirect('manage_requests')
    form = MarkPaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please correct the errors below.')
        return redirect('manage_requests')
    total_fee = sum(item.total_fee for item in doc_request.items.all())
    firestore_db.update_document_request(doc_request.pk, {
        'payment_status': 'paid',
        'paid_at': firestore_db.utcnow(),
        'payment_method': form.cleaned_data['payment_method'],
        'or_number': form.cleaned_data.get('or_number', '') or '',
    })
    notify(
        doc_request.resident_id,
        'Payment Confirmed',
        f'Your payment of \u20b1{total_fee:,.2f} for request '
        f'{doc_request.request_number} has been received.',
        link=reverse('request_history'),
    )
    resident = doc_request.resident
    if resident is not None:
        send_user_email(
            resident,
            'Payment Confirmed',
            f'Your payment of \u20b1{total_fee:,.2f} for request '
            f'{doc_request.request_number} has been received. Thank you!',
        )
    log_activity(request.user, 'Payment Collected',
                 f'Payment recorded for {doc_request.request_number}.', request,
                 subject_user_id=doc_request.resident_id)
    messages.success(request, f'Payment recorded for {doc_request.request_number}.')
    return redirect('manage_requests')


@login_required
@role_required('staff')
def reject_request(request, pk):
    doc_request = _request_or_404(pk)
    if not doc_request.barangay or doc_request.barangay.pk != request.user.barangay_id:
        raise Http404
    if request.method == 'POST':
        if 'rejected' not in [c for c, _ in _status_choices_for(doc_request.status)]:
            messages.error(
                request,
                f'Request {doc_request.request_number} cannot be rejected in its current state.'
            )
            return redirect('manage_requests')
        reason = request.POST.get('rejection_reason', '').strip()
        if not reason:
            messages.error(request, 'A rejection reason is required.')
            return redirect('manage_requests')
        _apply_status_transition(
            doc_request, 'rejected', request.user,
            request=request, rejection_reason=reason,
        )
        messages.success(request, f'Request {doc_request.request_number} has been rejected.')
        return redirect('manage_requests')
    return redirect('manage_requests')


@login_required
@role_required('staff')
def staff_reports(request):
    brgy = request.user.barangay
    doc_requests = requests_for_barangay(brgy.pk)

    # Daily stats for last 30 days
    today = timezone.localdate()
    day_counts = {}
    for req in doc_requests:
        if req.created_at is None:
            continue
        day = req.created_at.date()
        entry = day_counts.setdefault(day, {'count': 0, 'completed': 0})
        entry['count'] += 1
        if req.status == 'completed':
            entry['completed'] += 1
    daily_stats = [
        {'date': today - timedelta(days=i), 'count': day_counts.get(today - timedelta(days=i), {}).get('count', 0),
         'completed': day_counts.get(today - timedelta(days=i), {}).get('completed', 0)}
        for i in range(30)
    ]

    # Status breakdown
    status_counts = {}
    for req in doc_requests:
        status_counts[req.status] = status_counts.get(req.status, 0) + 1
    status_breakdown = [{'status': s, 'count': c} for s, c in status_counts.items()]

    # Document type breakdown
    doc_type_counts = {}
    for req in doc_requests:
        for item in req.items.all():
            name = item.document_type.name if item.document_type else 'Unknown'
            doc_type_counts[name] = doc_type_counts.get(name, 0) + 1
    doc_type_breakdown = [
        {'document_type__name': name, 'count': count}
        for name, count in sorted(doc_type_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # Total fees actually collected (from paid requests)
    total_fees = 0
    paid_count = 0
    for req in doc_requests:
        if req.is_paid:
            for item in req.items.all():
                total_fees += item.total_fee
            paid_count += 1

    # Monthly stats for last 12 months
    monthly_counts = {}
    for req in doc_requests:
        if req.created_at is None:
            continue
        key = (req.created_at.year, req.created_at.month)
        monthly_counts[key] = monthly_counts.get(key, 0) + 1
    monthly_stats = []
    for i in range(12):
        first = today.replace(day=1) - timedelta(days=28 * i)
        key = (first.year, first.month)
        monthly_stats.append({'month': first.replace(day=1), 'count': monthly_counts.get(key, 0)})

    return render(request, 'brgy/staff/reports.html', {
        'page_title': 'Reports',
        'brgy': brgy,
        'daily_stats': daily_stats,
        'status_breakdown': status_breakdown,
        'doc_type_breakdown': doc_type_breakdown,
        'total_fees': total_fees,
        'paid_count': paid_count,
        'monthly_stats': monthly_stats,
    })


@login_required
@role_required('staff')
def staff_reports_export(request):
    brgy = request.user.barangay
    doc_requests = requests_for_barangay(brgy.pk)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="barangay_reports_{brgy.pk[:8] if brgy.pk else "brgy"}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        'Request Number', 'Date Submitted', 'Resident', 'Email', 'Documents',
        'Purpose', 'Contact Number', 'Pickup Date', 'Pickup Slot', 'Status', 'Total Fee',
        'Payment', 'Payment Method', 'OR Number', 'Processed By', 'Staff Notes',
    ])
    total_fees = 0
    paid_count = 0
    for req in doc_requests:
        documents = '; '.join(
            f'{item.document_type.name}{" x" + str(item.quantity) if item.quantity and item.quantity > 1 else ""}'
            for item in req.items.all() if item.document_type
        )
        fee = sum(item.total_fee for item in req.items.all())
        if req.is_paid:
            total_fees += fee
            paid_count += 1
        writer.writerow([
            req.request_number,
            req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else '',
            req.resident.display_name if req.resident else '',
            req.resident.email if req.resident else '',
            documents,
            req.purpose or '',
            req.contact_number or '',
            req.pickup_date.strftime('%Y-%m-%d') if req.pickup_date else '',
            req.get_pickup_slot_display() if req.pickup_date else '',
            req.get_status_display(),
            f'{fee:.2f}',
            req.get_payment_status_display(),
            req.payment_method or '',
            req.or_number or '',
            req.processed_by.display_name if req.processed_by else '',
            req.staff_notes or '',
        ])
    writer.writerow([])
    writer.writerow(['TOTAL FEES (paid requests)', f'{total_fees:.2f}'])
    writer.writerow(['PAID REQUESTS COUNT', f'{paid_count}'])
    return response


@login_required
@role_required('staff')
def staff_manage_document_types(request):
    brgy = request.user.barangay
    doc_types = [DocumentType(d) for d in firestore_db.list_document_types(order_by='name')]
    local_types = [d for d in doc_types if not d.is_global and d.barangay_id == brgy.pk]
    global_types = [d for d in doc_types if d.is_global]
    search = request.GET.get('search', '')
    if search:
        local_types = [d for d in local_types if search.lower() in (d.name or '').lower()]
        global_types = [d for d in global_types if search.lower() in (d.name or '').lower()]

    overrides = {
        o.document_type_id: o
        for o in (DocumentTypeOverride(o) for o in firestore_db.list_document_type_overrides(
            filters=[('barangay_id', '==', brgy.pk)]
        ))
    }
    for dt in global_types:
        # Non-underscore names: Django templates refuse attribute traversal
        # starting with an underscore.  Set as real instance attributes so the
        # wrapper's _data dict (which is written to Firestore on save()) stays
        # clean.
        object.__setattr__(dt, 'override', overrides.get(dt.pk))
        object.__setattr__(dt, 'effective_fee', float(dt.override.fee or 0) if dt.override else 0)
    for dt in local_types + global_types:
        object.__setattr__(dt, 'tokens', _token_sheet(dt, getattr(dt, 'override', None)))

    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, request.FILES)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if form.is_valid():
            doc = form.save(barangay_id=brgy.pk)
            log_activity(request.user, 'Document Type Created',
                         f'Created document type "{form.cleaned_data["name"]}".', request)
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'doc': {
                        'pk': str(doc.pk),
                        'name': doc.name,
                        'description': doc.description or '',
                        'fee': float(doc.fee) if doc.fee else None,
                        'is_active': doc.is_active,
                        'requirements_count': len(doc.requirements_list) if doc.requirements_list else 0,
                        'edit_url': reverse('staff_edit_document_type', args=[str(doc.pk)]),
                    },
                })
            messages.success(request, f'{form.cleaned_data["name"]} added successfully.')
            return redirect('staff_manage_document_types')
        if is_ajax:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm()

    paginator = Paginator(local_types + global_types, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/staff/document_types.html', {
        'page_obj': page_obj, 'form': form, 'search': search, 'brgy': brgy,
        'page_title': 'Document Types',
    })


@login_required
@role_required('staff')
def staff_edit_document_type(request, pk):
    brgy = request.user.barangay
    doc_type = _doc_type_or_404(pk)
    if doc_type.is_global or doc_type.barangay_id != brgy.pk:
        raise Http404
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, request.FILES, instance=doc_type)
        
        if form.is_valid():
            # Availability is managed from the document list switch, not this form.
            form.cleaned_data['is_active'] = doc_type.is_active
            form.save(barangay_id=brgy.pk)
            log_activity(request.user, 'Document Type Updated',
                         f'Updated document type "{doc_type.name}".', request)
            messages.success(request, f'{doc_type.name} updated successfully.')
            return redirect('staff_manage_document_types')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(instance=doc_type)
    object.__setattr__(doc_type, 'tokens', _token_sheet(doc_type))
    return render(request, 'brgy/staff/document_type_form.html', {
        'form': form, 'doc_type': doc_type, 'title': f'Edit - {doc_type.name}',
        'brgy': brgy, 'page_title': f'Edit - {doc_type.name}',
    })


@login_required
@role_required('staff')
def staff_delete_document_type(request, pk):
    brgy = request.user.barangay
    doc_type = _doc_type_or_404(pk)
    if doc_type.is_global or doc_type.barangay_id != brgy.pk:
        raise Http404
    if request.method == 'POST':
        name = doc_type.name
        referenced = firestore_db.list_document_request_items(
            filters=[('document_type_id', '==', doc_type.pk)]
        )
        if referenced:
            messages.error(
                request,
                f'Cannot delete "{name}": it is used by existing document requests. '
                'Reject or complete those requests first.'
            )
            return redirect('staff_manage_document_types')
        firestore_db.delete_document_type(doc_type.pk)
        _delete_template_file(doc_type)
        log_activity(request.user, 'Document Type Deleted', f'Deleted document type "{name}".', request)
        messages.success(request, f'Document type "{name}" deleted successfully.')
    else:
        messages.error(request, 'Invalid request.')
    return redirect('staff_manage_document_types')


@login_required
@role_required('staff')
def staff_toggle_document_type(request, pk):
    """Flip a local document type's availability for the staff member's barangay."""
    brgy = request.user.barangay
    doc_type = _doc_type_or_404(pk)
    if doc_type.is_global or doc_type.barangay_id != brgy.pk:
        raise Http404
    if request.method == 'POST':
        new_active = not doc_type.is_active
        firestore_db.update_document_type(doc_type.pk, {'is_active': new_active})
        state = 'available' if new_active else 'unavailable'
        log_activity(
            request.user, 'Document Type Updated',
            f'Marked document type "{doc_type.name}" as {state}.', request,
        )
        messages.success(request, f'"{doc_type.name}" is now {state}.')
    else:
        messages.error(request, 'Invalid request.')
    return redirect('staff_manage_document_types')


@login_required
@role_required('staff')
def staff_edit_global_type(request, pk):
    """Staff configures the price/template of a global type for their own barangay."""
    brgy = request.user.barangay
    doc_type = _doc_type_or_404(pk)
    if not doc_type.is_global:
        raise Http404
    override_docs = firestore_db.list_document_type_overrides(
        filters=[('document_type_id', '==', doc_type.pk), ('barangay_id', '==', brgy.pk)]
    )
    override = DocumentTypeOverride(override_docs[0]) if override_docs else None

    if request.method == 'POST':
        form = GlobalTypeOverrideForm(request.POST, request.FILES, instance=override)
        if form.is_valid():
            form.save(override=override, document_type_id=doc_type.pk, barangay_id=brgy.pk)
            log_activity(request.user, 'Global Type Configured',
                         f'Configured "{doc_type.name}" for {brgy.name}.', request)
            messages.success(request, f'{doc_type.name} configured for {brgy.name}.')
            return redirect('staff_manage_document_types')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = GlobalTypeOverrideForm(instance=override)
    object.__setattr__(doc_type, 'tokens', _token_sheet(doc_type, override))
    return render(request, 'brgy/staff/global_type_form.html', {
        'form': form, 'doc_type': doc_type, 'override': override, 'brgy': brgy,
        'page_title': f'Configure - {doc_type.name}',
    })


@login_required
@role_required('staff')
def mark_printed(request, req_pk, item_pk):
    """POST-only: transition a request/document item to 'printed'.

    Moving state is a write operation and must be a CSRF-protected POST.
    Printing the document (GET) itself is kept read-only.
    """
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('manage_requests')
    doc_req = _request_or_404(req_pk)
    if not doc_req.barangay or doc_req.barangay.pk != request.user.barangay_id:
        raise Http404
    item = _item_or_404(item_pk)
    if item.request_id != doc_req.pk:
        raise Http404

    if doc_req.status == 'approved':
        _apply_status_transition(doc_req, 'printed', request.user, request=request)
    item_code = getattr(item, 'verification_code', None)
    if not item.is_printed:
        # Mint a unique per-document verification reference on first print.
        if not item_code:
            item_code = _make_verification_code()
        firestore_db.update_document_request_item(item.pk, {
            'printed_at': firestore_db.utcnow(),
            'verification_code': item_code,
        })
        log_activity(
            request.user,
            'Document Printed',
            f'Printed document "{getattr(item.document_type, "name", "document")}" '
            f'for request {doc_req.request_number}. Verification: {item_code}.',
            request,
            subject_user_id=doc_req.resident_id,
        )
    elif not item_code:
        # Item was printed before per-document codes existed; backfill one.
        item_code = _make_verification_code()
        firestore_db.update_document_request_item(item.pk, {'verification_code': item_code})
    return redirect('print_document', req_pk=doc_req.pk, item_pk=item.pk)


@login_required
@role_required('staff')
def print_document(request, req_pk, item_pk):
    doc_req = _request_or_404(req_pk)
    if not doc_req.barangay or doc_req.barangay.pk != request.user.barangay_id:
        raise Http404
    item = _item_or_404(item_pk)
    if item.request_id != doc_req.pk:
        raise Http404

    doc_type = item.document_type
    if not doc_type:
        messages.error(request, 'Document type not found.')
        return redirect('manage_requests')

    if doc_type.is_global:
        barangay = doc_req.barangay
        override = get_override_for(doc_type.pk, barangay.pk if barangay else None)
        if not override or not override.has_template:
            messages.error(request, f'No Word template configured for {doc_type.name} in {barangay.name if barangay else "this barangay"}.')
            return redirect('manage_requests')
        template_path = override.template_file.path
    else:
        if not doc_type.has_template:
            messages.error(request, f'No Word template uploaded for {doc_type.name}.')
            return redirect('manage_requests')
        template_path = doc_type.template_file.path

    if not os.path.exists(template_path):
        messages.error(request, f'Template file for {doc_type.name} is missing.')
        return redirect('manage_requests')

    item_code = _item_verification_code(item, doc_req)
    verify_url = _absolute_url(
        request, reverse('verify_document') + '?code=' + item_code
    ) if item_code else ''
    namespace = _build_template_context(
        resident=doc_req.resident, barangay=doc_req.barangay, doc_req=doc_req,
        item=item, doc_type=doc_type, verification_code=item_code or 'N/A',
        verify_url=verify_url,
    )
    if doc_type.is_global:
        variables = _template_detected_variables(doc_type, override)
    else:
        variables = _template_detected_variables(doc_type)
    token_salt = _doc_template_salt(doc_type)
    if variables is None:
        variables = _live_template_variables(template_path, token_salt)
    context = _resolve_template_context(namespace, variables, token_salt=token_salt)
    _inject_token_values(
        context, namespace, doc_type,
        override if doc_type.is_global else None,
    )

    doc = DocxTemplate(template_path)
    doc.render(context)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
# Read-only download: no state is mutated here.  Staff mark the request as
    # printed via the POST 'mark_printed' action, then this GET delivers the file.
    resident = doc_req.resident
    filename = f"{doc_type.name}_{resident.last_name if resident else 'resident'}_{doc_req.request_number}.docx"
    response = FileResponse(
        file_stream,
        as_attachment=True,
        filename=filename,
    )
    response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return response


@login_required
@role_required('staff')
def requirement_file(request, req_pk, item_pk, index):
    """Download a resident's attached requirement file for a request item."""
    doc_req = _request_or_404(req_pk)
    if not doc_req.barangay or doc_req.barangay.pk != request.user.barangay_id:
        raise Http404
    item = _item_or_404(item_pk)
    if item.request_id != doc_req.pk:
        raise Http404
    files = getattr(item, 'requirement_files') or []
    if index < 0 or index >= len(files):
        raise Http404
    rel_path = files[index]
    file_path = os.path.join(settings.MEDIA_ROOT, rel_path)
    if not os.path.isfile(file_path):
        raise Http404
    log_activity(
        request.user,
        'Requirement File Viewed',
        f'Viewed a requirement file for request {doc_req.request_number}.',
        request,
        subject_user_id=doc_req.resident_id,
    )
    return FileResponse(open(file_path, 'rb'), as_attachment=True)


# ═══════════════════════════════════════════════════════════════
# ADMIN VIEWS
# ═══════════════════════════════════════════════════════════════

@login_required
@role_required('admin')
def admin_dashboard(request):
    all_users = firestore_db.list_users()
    residents = [u for u in all_users if u.get('role') == 'resident']
    staff = [u for u in all_users if u.get('role') == 'staff']
    total_residents = len(residents)
    verified_residents = len([u for u in residents if u.get('verification_status') == 'approved'])
    total_staff = len(staff)
    active_staff = len([u for u in staff if u.get('is_active')])

    barangays = [Barangay(b) for b in firestore_db.list_barangays()]
    total_barangays = len([b for b in barangays if b.is_active])
    pending_verifications = len([u for u in residents if u.get('verification_status') == 'pending'])

    all_requests = [DocumentRequest(r) for r in firestore_db.list_document_requests()]
    total_requests = len(all_requests)
    pending_requests = sum(1 for r in all_requests if r.status == 'pending')
    completed_requests = sum(1 for r in all_requests if r.status == 'completed')

    recent_logs = [
        ActivityLog(l) for l in firestore_db.list_activity_logs(order_by='created_at', descending=True, limit=10)
    ]

    barangay_dict = {b.pk: b for b in barangays}

    barangay_stats = []
    for brgy in barangays:
        if brgy.is_active:
            brgy.total_residents = len([
                u for u in residents if u.get('barangay_id') == brgy.pk
                and u.get('verification_status') == 'approved'
            ])
            brgy.total_requests = 0
            barangay_stats.append(brgy)

    resident_barangay_ids = {}
    for u in residents:
        resident_barangay_ids[u.get('id')] = u.get('barangay_id')
    for req in all_requests:
        brgy_id = resident_barangay_ids.get(req.resident_id)
        if brgy_id and barangay_dict.get(brgy_id) and barangay_dict[brgy_id].is_active:
            barangay_dict[brgy_id].total_requests += 1

    barangay_stats.sort(key=lambda b: b.total_requests, reverse=True)
    barangay_stats = barangay_stats[:5]

    monthly_counts = {}
    for req in all_requests:
        if req.created_at is None:
            continue
        key = (req.created_at.year, req.created_at.month)
        monthly_counts[key] = monthly_counts.get(key, 0) + 1

    # Random starting point for the trend-bar color palette so each
    # dashboard load cycles the bars to a fresh set of gradients.
    trend_palette = ['trend-c1', 'trend-c2', 'trend-c3', 'trend-c4', 'trend-c5', 'trend-c6']
    palette_offset = random.randrange(len(trend_palette))

    monthly_trend = []
    today = timezone.localdate()
    year, month = today.year, today.month
    for i in range(6):
        m = month - i
        y = year
        while m < 1:
            m += 12
            y -= 1
        key = (y, m)
        monthly_trend.append({
            'month': date(y, m, 1),
            'count': monthly_counts.get(key, 0),
            'bar_class': trend_palette[(palette_offset + i) % len(trend_palette)],
        })

    trend_counts = [m['count'] for m in monthly_trend]
    trend_max_count = max(trend_counts) or 1
    trend_total = sum(trend_counts)
    trend_avg = round(trend_total / len(trend_counts)) if trend_counts else 0
    trend_delta = trend_counts[0] - trend_counts[1] if len(trend_counts) >= 2 else 0
    trend_best = max(monthly_trend, key=lambda m: m['count']) if trend_counts else None

    return render(request, 'brgy/admin/dashboard.html', {
        'page_title': 'Admin Dashboard',
        'total_residents': total_residents,
        'verified_residents': verified_residents,
        'total_staff': total_staff,
        'active_staff': active_staff,
        'total_barangays': total_barangays,
        'pending_verifications': pending_verifications,
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'completed_requests': completed_requests,
        'recent_logs': recent_logs,
        'barangay_stats': barangay_stats,
        'monthly_trend': monthly_trend,
        'trend_max_count': trend_max_count,
        'trend_total': trend_total,
        'trend_avg': trend_avg,
        'trend_delta': trend_delta,
        'trend_best': trend_best,
    })


def _admin_reports_scope(request):
    """Build the filtered set of document requests for system-wide reporting,
    attributing each request to its resident's barangay."""
    requests = [DocumentRequest(r) for r in firestore_db.list_document_requests()]
    residents = firestore_db.get_users_bulk({r.resident_id for r in requests if r.resident_id})
    for req in requests:
        resident = residents.get(req.resident_id)
        object.__setattr__(req, '_resident_brgy_id', resident.get('barangay_id') if resident else None)
        object.__setattr__(req, '_resident_name', resident.get('first_name', '') if resident else '')
        object.__setattr__(req, '_resident_last', resident.get('last_name', '') if resident else '')
        object.__setattr__(req, '_resident_email', resident.get('email', '') if resident else '')

    barangay_filter = request.GET.get('barangay', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    status_filter = request.GET.get('status', '')
    from_date = to_date = None
    try:
        from_date = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
    except ValueError:
        pass
    try:
        to_date = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
    except ValueError:
        pass

    def _matches(r):
        if barangay_filter and r._resident_brgy_id != barangay_filter:
            return False
        if status_filter and r.status != status_filter:
            return False
        if from_date and (r.created_at is None or r.created_at.date() < from_date):
            return False
        if to_date and (r.created_at is None or r.created_at.date() > to_date):
            return False
        return True

    filters = {
        'barangay': barangay_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status': status_filter,
    }
    return [r for r in requests if _matches(r)], filters


@login_required
@role_required('admin')
def admin_reports(request):
    filtered, filters = _admin_reports_scope(request)
    barangays = [Barangay(b) for b in firestore_db.list_barangays(order_by='name')]

    total_requests = len(filtered)
    status_counts = {}
    total_fees = 0.0
    paid_count = 0
    pending = 0
    completed = 0
    for r in filtered:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        if r.status == 'pending':
            pending += 1
        elif r.status == 'completed':
            completed += 1
        if r.is_paid:
            paid_count += 1
            total_fees += r.total_fee

    status_labels = dict(DocumentRequest.Status.choices)
    status_pill_classes = {
        'ready_for_pickup': 'ready',
        'cancelled': 'cancelled',
        'approved': 'approved',
        'printed': 'printed',
        'completed': 'completed',
        'rejected': 'rejected',
        'pending': 'pending',
    }
    status_breakdown = []
    for s, c in sorted(status_counts.items(), key=lambda kv: kv[1], reverse=True):
        status_breakdown.append({
            'status': s,
            'count': c,
            'label': status_labels.get(s, s.title()),
            'pill_class': status_pill_classes.get(s, s),
            'pct': round(c * 100 / total_requests, 1) if total_requests else 0,
        })

    total_fees_fmt = f'{total_fees:,.2f}'
    completion_rate = round(completed * 100 / total_requests) if total_requests else 0

    per_barangay = []
    for b in barangays:
        brgy_requests = [r for r in filtered if r._resident_brgy_id == b.pk]
        if not brgy_requests:
            continue
        fees = sum(r.total_fee for r in brgy_requests if r.is_paid)
        per_barangay.append({
            'barangay': b,
            'count': len(brgy_requests),
            'pending': sum(1 for r in brgy_requests if r.status == 'pending'),
            'completed': sum(1 for r in brgy_requests if r.status == 'completed'),
            'paid': sum(1 for r in brgy_requests if r.is_paid),
            'fees': fees,
            'pct': round(len(brgy_requests) * 100 / total_requests, 1) if total_requests else 0,
            'fees_fmt': f'{fees:,.2f}',
        })
    per_barangay.sort(key=lambda x: x['count'], reverse=True)

    doc_type_counts = {}
    for r in filtered:
        for item in r.items.all():
            name = item.document_type.name if item.document_type else 'Unknown'
            doc_type_counts[name] = doc_type_counts.get(name, 0) + 1
    doc_type_breakdown = [
        {'document_type__name': name, 'count': count}
        for name, count in sorted(doc_type_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    monthly_counts = {}
    for r in filtered:
        if r.created_at is None:
            continue
        key = (r.created_at.year, r.created_at.month)
        monthly_counts[key] = monthly_counts.get(key, 0) + 1
    today = timezone.localdate()
    monthly_stats = []
    for i in range(12):
        month_start = (today.replace(day=1) - timedelta(days=28 * i)).replace(day=1)
        monthly_stats.append({
            'month': month_start,
            'count': monthly_counts.get((month_start.year, month_start.month), 0),
        })
    monthly_counts_list = [m['count'] for m in monthly_stats]
    monthly_max = max(monthly_counts_list) or 1
    monthly_total = sum(monthly_counts_list)
    monthly_avg = round(monthly_total / len(monthly_counts_list)) if monthly_counts_list else 0
    monthly_peak_index = monthly_counts_list.index(max(monthly_counts_list)) if monthly_counts_list else 0

    barangay_by_pk = {b.pk: b.name for b in barangays}
    filter_summary = []
    if filters['barangay']:
        filter_summary.append(barangay_by_pk.get(filters['barangay'], 'Selected barangay'))
    if filters['status']:
        filter_summary.append(status_labels.get(filters['status'], filters['status'].title()))
    if filters['date_from']:
        filter_summary.append(f'From {filters["date_from"]}')
    if filters['date_to']:
        filter_summary.append(f'To {filters["date_to"]}')

    return render(request, 'brgy/admin/reports.html', {
        'page_title': 'System Reports',
        'filters': filters,
        'barangays': barangays,
        'total_requests': total_requests,
        'total_fees': total_fees,
        'total_fees_fmt': total_fees_fmt,
        'completion_rate': completion_rate,
        'paid_count': paid_count,
        'pending': pending,
        'completed': completed,
        'status_breakdown': status_breakdown,
        'status_choices': DocumentRequest.Status.choices,
        'per_barangay': per_barangay,
        'doc_type_breakdown': doc_type_breakdown,
        'monthly_stats': monthly_stats,
        'monthly_max': monthly_max,
        'monthly_total': monthly_total,
        'monthly_avg': monthly_avg,
        'monthly_peak_index': monthly_peak_index,
        'monthly_peak_month': monthly_stats[monthly_peak_index]['month'],
        'monthly_peak_count': monthly_stats[monthly_peak_index]['count'],
        'filter_summary': filter_summary,
    })


@login_required
@role_required('admin')
def admin_reports_export(request):
    filtered, filters = _admin_reports_scope(request)
    brgy_names = {b['id']: b.get('name', '') for b in firestore_db.list_barangays()}

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="system_reports.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Request Number', 'Date Submitted', 'Barangay', 'Resident', 'Email',
        'Documents', 'Purpose', 'Status', 'Total Fee', 'Payment', 'Payment Method',
        'OR Number', 'Processed By',
    ])
    total_fees = 0
    paid_count = 0
    for req in filtered:
        documents = '; '.join(
            f'{item.document_type.name}{" x" + str(item.quantity) if item.quantity and item.quantity > 1 else ""}'
            for item in req.items.all() if item.document_type
        )
        fee = req.total_fee
        if req.is_paid:
            total_fees += fee
            paid_count += 1
        writer.writerow([
            req.request_number,
            req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else '',
            brgy_names.get(req._resident_brgy_id, ''),
            f"{req._resident_name} {req._resident_last}".strip() or '',
            req._resident_email or '',
            documents,
            req.purpose or '',
            req.get_status_display(),
            f'{fee:.2f}',
            req.get_payment_status_display(),
            req.payment_method or '',
            req.or_number or '',
            req.processed_by.display_name if req.processed_by else '',
        ])
    writer.writerow([])
    writer.writerow(['TOTAL FEES (paid requests)', f'{total_fees:.2f}'])
    writer.writerow(['PAID REQUESTS COUNT', f'{paid_count}'])
    return response


@login_required
@role_required('admin')
def manage_staff(request):
    staff_users = [
        CustomUser(u) for u in firestore_db.list_users(
            filters=[('role', '==', 'staff')],
            order_by='date_joined',
            descending=True,
        )
    ]
    search = request.GET.get('search', '')
    if search:
        search = search.lower()
        staff_users = [
            s for s in staff_users
            if search in (s.first_name or '').lower()
            or search in (s.last_name or '').lower()
            or search in (s.email or '').lower()
            or (s.barangay and search in (s.barangay.name or '').lower())
        ]
    paginator = Paginator(staff_users, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            staff = form.save()
            log_activity(request.user, 'Staff Account Created', 'Staff account created.', request,
                         subject_user_id=staff.pk)
            messages.success(request, 'Staff account created successfully.')
            generated = getattr(staff, '_generated_password', None)
            if generated:
                messages.add_message(
                    request, messages.INFO, generated, extra_tags='generated-password'
                )
                send_welcome_email(staff.email, staff.display_name, generated)
            return redirect('manage_staff')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffCreationForm()
    has_barangays = len(list(firestore_db.list_barangays(active_only=True))) > 0
    return render(request, 'brgy/admin/manage_staff.html', {
        'page_obj': page_obj, 'form': form, 'search': search,
        'page_title': 'Manage Staff', 'has_barangays': has_barangays, 'creating': True,
    })


@login_required
@role_required('admin')
def edit_staff(request, pk):
    staff = _user_or_404(pk)
    if staff.role != 'staff':
        raise Http404
    if request.method == 'POST':
        form = StaffCreationForm(request.POST, instance=staff)
        if form.is_valid():
            form.save()
            log_activity(request.user, 'Staff Account Updated', 'Staff account updated.', request,
                         subject_user_id=staff.pk)
            messages.success(request, f'{staff.display_name} updated successfully.')
            return redirect('manage_staff')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffCreationForm(instance=staff)
    return render(request, 'brgy/admin/edit_staff.html', {'staff': staff, 'form': form, 'page_title': f'Edit Staff - {staff.display_name}', 'creating': False})


@login_required
@role_required('admin')
def reset_staff_password(request, pk):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('manage_staff')
    staff = _user_or_404(pk)
    if staff.role != 'staff':
        raise Http404
    temp_password = secrets.token_urlsafe(12)
    staff.set_password(temp_password)
    firestore_db.update_user(staff.pk, {'password': staff.password})
    log_activity(request.user, 'Staff Password Reset', 'Staff password reset.', request,
                 subject_user_id=staff.pk)
    messages.success(request, f'Temporary password generated for {staff.display_name}.')
    messages.add_message(
        request, messages.INFO, temp_password, extra_tags='generated-password'
    )
    send_welcome_email(staff.email, staff.display_name, temp_password)
    return redirect('manage_staff')


@login_required
@role_required('admin')
def toggle_staff_active(request, pk):
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('manage_staff')
    staff = _user_or_404(pk)
    if staff.role != 'staff':
        raise Http404
    new_status = not staff.is_active
    firestore_db.update_user(staff.pk, {'is_active': new_status})
    status = 'activated' if new_status else 'deactivated'
    log_activity(request.user, f'Staff {status}', f'Staff account {status}.', request,
                 subject_user_id=staff.pk)
    messages.success(request, f'{staff.display_name} has been {status}.')
    return redirect('manage_staff')


@login_required
@role_required('admin')
def manage_barangays(request):
    barangays = [Barangay(b) for b in firestore_db.list_barangays(order_by='created_at', descending=True)]
    search = request.GET.get('search', '')
    if search:
        search = search.lower()
        barangays = [
            b for b in barangays
            if search in (b.name or '').lower() or search in (b.address or '').lower()
        ]
    paginator = Paginator(barangays, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = BarangayForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            log_activity(request.user, 'Barangay Created',
                         f'Created barangay "{form.cleaned_data["name"]}".', request)
            messages.success(request, 'Barangay added successfully.')
            return redirect('manage_barangays')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = BarangayForm()
    return render(request, 'brgy/admin/manage_barangays.html', {'page_obj': page_obj, 'form': form, 'search': search, 'page_title': 'Manage Barangays'})


@login_required
@role_required('admin')
def edit_barangay(request, pk):
    barangay = _brgy_or_404(pk)
    if request.method == 'POST':
        form = BarangayForm(request.POST, request.FILES, instance=barangay)
        if form.is_valid():
            form.save()
            log_activity(request.user, 'Barangay Updated',
                         f'Updated barangay "{barangay.name}".', request)
            messages.success(request, f'{barangay.name} updated successfully.')
            return redirect('manage_barangays')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = BarangayForm(instance=barangay)
    return render(request, 'brgy/admin/edit_barangay.html', {'barangay': barangay, 'form': form, 'page_title': 'Edit Barangay'})


@login_required
@role_required('admin')
def change_barangay_logo(request, pk):
    barangay = _brgy_or_404(pk)
    if request.method == 'POST':
        logo = request.FILES.get('logo')
        if logo:
            try:
                path = _save_uploaded_file(
                    logo, 'barangay_logos', IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'logo',
                )
            except ValidationError as e:
                messages.error(request, ' '.join(e.messages))
                return redirect('manage_barangays')
            firestore_db.update_barangay(barangay.pk, {'logo': path})
            log_activity(request.user, 'Barangay Logo Updated', f'Logo updated for {barangay.name}.', request)
            messages.success(request, f'Logo for {barangay.name} updated successfully.')
        else:
            messages.error(request, 'Please select an image file to use as the logo.')
    return redirect('manage_barangays')


@login_required
@role_required('admin')
def manage_document_types(request):
    doc_types = [DocumentType(d) for d in firestore_db.list_document_types(order_by='created_at', descending=True)]
    search = request.GET.get('search', '')
    brgy_filter = request.GET.get('barangay', '')
    if search:
        doc_types = [d for d in doc_types if search.lower() in (d.name or '').lower()]
    if brgy_filter:
        doc_types = [d for d in doc_types if not d.is_global and d.barangay_id == brgy_filter]
    paginator = Paginator(doc_types, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    for dt in doc_types:
        # Same underscore-guard pattern as the staff list: real attributes so
        # the wrapper's _data dict stays clean for Firestore writes.
        object.__setattr__(dt, 'tokens', _token_sheet(dt))
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, metadata_only=True)
        if form.is_valid():
            form.save()
            log_activity(request.user, 'Document Type Created',
                         f'Created document type "{form.cleaned_data["name"]}".', request)
            messages.success(request, 'Document type added successfully.')
            return redirect('manage_document_types')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(metadata_only=True)
    barangays = [Barangay(b) for b in firestore_db.list_barangays(active_only=True)]
    return render(request, 'brgy/admin/document_types.html', {
        'page_obj': page_obj, 'form': form, 'search': search,
        'brgy_filter': brgy_filter, 'barangays': barangays,
        'page_title': 'Document Types',
    })


@login_required
@role_required('admin')
def edit_document_type(request, pk):
    doc_type = _doc_type_or_404(pk)
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, instance=doc_type, metadata_only=True)
        if form.is_valid():
            new_scope = form.cleaned_data.get('scope', 'local')
            if doc_type.is_global and new_scope == 'local':
                for o in firestore_db.list_document_type_overrides(
                    filters=[('document_type_id', '==', doc_type.pk)]
                ):
                    _delete_template_file(DocumentTypeOverride(o))
                    firestore_db.delete_document_type_override(o['id'])
            form.save()
            log_activity(request.user, 'Document Type Updated',
                         f'Updated document type "{doc_type.name}".', request)
            messages.success(request, f'{doc_type.name} updated successfully.')
            return redirect('manage_document_types')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(instance=doc_type, metadata_only=True)
    object.__setattr__(doc_type, 'tokens', _token_sheet(doc_type))
    return render(request, 'brgy/admin/edit_document_type.html', {'doc_type': doc_type, 'form': form, 'page_title': f'Edit Document Type - {doc_type.name}'})


@login_required
@role_required('admin')
def delete_document_type(request, pk):
    doc_type = _doc_type_or_404(pk)
    if request.method == 'POST':
        name = doc_type.name
        referenced = firestore_db.list_document_request_items(
            filters=[('document_type_id', '==', doc_type.pk)]
        )
        if referenced:
            messages.error(
                request,
                f'Cannot delete "{name}": it is used by existing document requests. '
                'Reject or complete those requests first.'
            )
            return redirect('manage_document_types')
        if doc_type.is_global:
            for o in firestore_db.list_document_type_overrides(
                filters=[('document_type_id', '==', doc_type.pk)]
            ):
                _delete_template_file(DocumentTypeOverride(o))
                firestore_db.delete_document_type_override(o['id'])
        firestore_db.delete_document_type(doc_type.pk)
        _delete_template_file(doc_type)
        log_activity(request.user, 'Document Type Deleted', f'Deleted document type "{name}".', request)
        messages.success(request, f'Document type "{name}" deleted successfully.')
    else:
        messages.error(request, 'Invalid request.')
    return redirect('manage_document_types')


@login_required
@role_required('admin')
def activity_logs(request):
    action_filter = request.GET.get('action', '')
    search = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    barangay_filter = request.GET.get('barangay', '')
    logs = _filtered_activity_logs(search, action_filter, date_from, date_to, barangay_filter)
    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    barangays = [Barangay(b) for b in firestore_db.list_barangays(active_only=True)]
    return render(request, 'brgy/admin/activity_logs.html', {
        'page_obj': page_obj,
        'page_title': 'Activity Logs',
        'action_filter': action_filter,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'barangay_filter': barangay_filter,
        'barangays': barangays,
    })


def _filtered_activity_logs(search='', action='', date_from='', date_to='', barangay=''):
    """Return activity logs matching the given admin filters (shared by the
    logs page and the CSV export)."""
    logs = [ActivityLog(l) for l in firestore_db.list_activity_logs(order_by='created_at', descending=True)]
    if action:
        logs = [l for l in logs if action.lower() in (l.action or '').lower()]
    if search:
        search = search.lower()
        logs = [
            l for l in logs
            if search in (l.action or '').lower()
            or search in (l.details or '').lower()
            or (l.user and (search in (l.user.first_name or '').lower()
                            or search in (l.user.last_name or '').lower()))
        ]
    if barangay:
        logs = [l for l in logs if l._data.get('barangay_id') == barangay]
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            logs = [l for l in logs if l.created_at is not None and l.created_at.date() >= from_date]
        except ValueError:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            logs = [l for l in logs if l.created_at is not None and l.created_at.date() <= to_date]
        except ValueError:
            pass
    return logs


@login_required
@role_required('admin')
def activity_logs_export(request):
    action_filter = request.GET.get('action', '')
    search = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    barangay_filter = request.GET.get('barangay', '')
    logs = _filtered_activity_logs(search, action_filter, date_from, date_to, barangay_filter)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="activity_logs.csv"'
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'User', 'Role', 'Barangay', 'Action', 'Details', 'IP Hash'])
    for log in logs:
        writer.writerow([
            log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
            log.user.display_name if log.user else 'System',
            log.user.get_role_display() if log.user else 'System',
            log.barangay.name if log.barangay else '',
            log.action or '',
            log.details or '',
            (log._data.get('ip_hash') or '')[:16],
        ])
    return response
