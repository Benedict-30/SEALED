"""
Firestore data access layer.

All persistence for the barangay document system goes through Cloud
Firestore using the Firebase Admin SDK. This module replaces the Django ORM.

Queries intentionally avoid composite Firestore indexes (which must be
created manually in the console). Data is fetched with the auto-indexed
single-field equality operators where useful, and any remaining filtering and
sorting happens in Python. This is fine for a barangay-scale application.
"""
import functools
import logging
import queue
import sys
import threading
import time as _time
import uuid
from concurrent.futures import Future, TimeoutError as FutureTimeout
from datetime import date, datetime, time, timedelta, timezone

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

logger = logging.getLogger(__name__)

_COLLECTION_NAMES = {
    'barangay': 'barangays',
    'user': 'users',
    'document_type': 'document_types',
    'document_type_override': 'document_type_overrides',
    'document_request': 'document_requests',
    'document_request_item': 'document_request_items',
    'notification': 'notifications',
    'activity_log': 'activity_logs',
    'login_attempt': 'login_attempts',
    'counter': 'counters',
    'announcement': 'announcements',
    'otp': 'otp_codes',
}

# Login OTP: verified via the user's email, valid for this many minutes.
LOGIN_OTP_TTL_MINUTES = 10

# Number of failed OTP attempts allowed before the pending login is discarded
# and the user must start again from the login page.
MAX_OTP_ATTEMPTS = 5

# Notifications are auto-deleted once they are older than this many days.
NOTIFICATION_TTL_DAYS = 7

# Login brute-force protection: after MAX_LOGIN_ATTEMPTS consecutive failures
# for the same key (username+IP), further attempts are blocked for the lockout
# window.
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15

# Lazy purge is debounced so notification reads don't scan+delete on every request.
_NOTIFICATION_CLEANUP_INTERVAL = timedelta(minutes=30)
_last_notification_cleanup = None

# Low-volatility lookups (document types, barangays) are memoized for a short
# window to avoid re-fetching the same list on every page load.  Writes clear
# the relevant key immediately so edits show up right away.
_LOW_VOLATILITY_TTL = 120
_CACHE_BARANGAYS = 'firestore:barangays'
_CACHE_DOCUMENT_TYPES = 'firestore:document_types'


def _cache_get(key):
    try:
        from django.core.cache import cache
        return cache.get(key)
    except Exception:
        return None


def _cache_set(key, value):
    try:
        from django.core.cache import cache
        cache.set(key, value, _LOW_VOLATILITY_TTL)
    except Exception:
        pass


def _cache_clear(key):
    try:
        from django.core.cache import cache
        cache.delete(key)
    except Exception:
        pass


# ─────────────────── Firestore availability guard ───────────────────
# The Firebase Admin SDK can hang on a dead/stale connection for minutes
# (transport-level retries are not bounded by the per-call ``timeout``
# kwarg), which used to freeze every page that touched Firestore.  Every
# network call now runs inside a worker thread with a hard deadline; after a
# deadline is hit the module latches a short fail-fast window so we don't
# pay a multi-second timeout on every request during an outage.  Reads
# degrade (empty/None), writes raise FirestoreUnavailableError so data is
# never silently dropped.

class FirestoreUnavailableError(Exception):
    """Firestore did not respond within the deadline (or is unreachable)."""

# Hard ceiling for a single Firestore round-trip.
FIRESTORE_TIMEOUT_SECONDS = 6
# After a detected outage, eagerly fail NEW calls for this long, then probe
# again so recovery is picked up automatically.
_FAILURE_LATCH_SECONDS = 60

class _DeadlineExecutor:
    """Small pool of daemon worker threads for running Firestore calls.

    Daemon workers ensure an abandoned call (one that exceeded its deadline
    and is still stuck inside the SDK) can never block interpreter shutdown.
    """

    def __init__(self, max_workers=4):
        self._work = queue.Queue()
        for _ in range(max_workers):
            t = threading.Thread(
                target=self._worker, daemon=True, name='firestore-deadline'
            )
            t.start()

    def _worker(self):
        while True:
            item = self._work.get()
            if item is None:
                return
            fn, fut = item
            try:
                fut.set_result(fn())
            except BaseException as exc:
                fut.set_exception(exc)

    def submit(self, fn):
        fut = Future()
        self._work.put((fn, fut))
        return fut


_executor = _DeadlineExecutor(max_workers=4)
_outage_since = None
_outage_lock = threading.Lock()
_last_logged_error = None


def _handle_outage(message):
    global _outage_since, _last_logged_error
    now = _time.monotonic()
    with _outage_lock:
        if _outage_since is None:
            _outage_since = now
            logger.error('Firestore outage: %s. Failing fast for next %ss.', message, _FAILURE_LATCH_SECONDS)
            _last_logged_error = now
        elif _last_logged_error is None or now - _last_logged_error > 60:
            logger.error('Firestore still unavailable: %s', message)
            _last_logged_error = now


def _clear_outage():
    global _outage_since
    with _outage_lock:
        _outage_since = None


def _in_failure_window():
    global _outage_since
    with _outage_lock:
        if _outage_since is None:
            return False
        if _time.monotonic() - _outage_since > _FAILURE_LATCH_SECONDS:
            _outage_since = None  # time to probe Firestore again
            return False
        return True


def _with_deadline(fn, timeout=FIRESTORE_TIMEOUT_SECONDS):
    """Run ``fn`` in a worker thread and wait at most ``timeout`` seconds.

    Raises FirestoreUnavailableError instead of hanging when Firestore is
    unreachable or slower than the deadline.
    """
    if _in_failure_window():
        raise FirestoreUnavailableError('Firestore unavailable (recent outage)')
    future = _executor.submit(fn)
    try:
        result = future.result(timeout=timeout)
    except FutureTimeout:
        _handle_outage(f'call exceeded {timeout}s deadline')
        raise FirestoreUnavailableError(
            f'Firestore request exceeded the {timeout}s deadline'
        )
    except Exception:
        _handle_outage(str(sys.exc_info()[1] or sys.exc_info()[0]))
        raise
    _clear_outage()
    return result


def outage_active():
    """True when Firestore has recently failed and reads are failing fast.

    Lets callers (e.g. the auth middleware) distinguish a Firestore outage
    from a genuinely missing record so they can keep a session cookie alive
    across an outage.
    """
    return _in_failure_window()


def _outage_safe(default=None):
    """Decorator: degrade to *default* instead of raising on Firestore trouble.

    Applied to best-effort security/notification bookkeeping (login throttling,
    OTP records) where a missing write must never take down a whole page during
    an outage.  Business data writes are deliberately NOT wrapped so nothing is
    silently lost.
    """
    def _decorator(fn):
        @functools.wraps(fn)
        def _wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.warning(
                    'Firestore unavailable during %s(); returning %r',
                    fn.__name__, default,
                )
                return default
        return _wrapped
    return _decorator


def get_db():
    return firestore.client()


def _to_firestore(value):
    """Convert Python values into Firestore-safe values (aware datetimes)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, dict):
        return {k: _to_firestore(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_firestore(v) for v in value]
    return value


def collection(name):
    return get_db().collection(_COLLECTION_NAMES[name])


def new_id():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


# ───────────────────────── Generic helpers ─────────────────────────

def create_doc(name, data, doc_id=None):
    """Create a document and return its id."""
    if doc_id is None:
        doc_id = new_id()
    doc_id = str(doc_id)
    data = dict(data)
    data.setdefault('created_at', utcnow())
    data.setdefault('updated_at', utcnow())

    def _write():
        collection(name).document(doc_id).set(_to_firestore(data))

    _with_deadline(_write)
    return doc_id


def update_doc(name, doc_id, data):
    """Merge updates into an existing document."""
    data = dict(data)
    data['updated_at'] = utcnow()

    def _write():
        collection(name).document(str(doc_id)).set(_to_firestore(data), merge=True)

    _with_deadline(_write)


def delete_doc(name, doc_id):
    def _write():
        collection(name).document(str(doc_id)).delete()

    _with_deadline(_write)


def get_doc(name, doc_id):
    """Return a document dict (with 'id') or None.

    Firestore being unreachable degrades to None so pages render (empty)
    instead of hanging.
    """
    def _fetch():
        return collection(name).document(str(doc_id)).get()

    try:
        snap = _with_deadline(_fetch)
    except Exception:
        if not _in_failure_window():
            logger.exception('Firestore get_doc(%s, %s) failed', name, doc_id)
        return None
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    data['id'] = snap.id
    return data


def _matches(doc, key, op, value):
    actual = doc.get(key)
    if op == '==':
        return actual == value
    if op == '!=':
        return actual != value
    if op == '>=':
        return actual is not None and actual >= value
    if op == '<':
        return actual is not None and actual < value
    return True


def list_docs(name, filters=None, order_by=None, descending=False, limit=None):
    """Return a list of document dicts (each with 'id').

    A single-field equality filter (``==``) is pushed down to Firestore, which
    auto-indexes individual fields, to cut data transfer for the common
    ``WHERE field == value`` lookups.  If more than one distinct field is
    equality-filtered, nothing is pushed (to guarantee we never require a
    composite index, which this project deliberately avoids).  All remaining
    filters and sorting happen in Python.

    A Firestore outage degrades to an empty list so read-only pages render
    instead of hanging.
    """
    query = collection(name)
    python_filters = list(filters or [])

    equal_fields = {key for key, op, _ in python_filters if op == '=='}
    if len(equal_fields) == 1:
        key = next(iter(equal_fields))
        value = next(v for k, op, v in python_filters if op == '==' and k == key)
        query = query.where(filter=FieldFilter(key, '==', value))
        python_filters = [
            (k, op, v) for k, op, v in python_filters
            if not (op == '==' and k == key)
        ]

    try:
        snapshots = _with_deadline(lambda: list(query.stream()))
    except Exception:
        if not _in_failure_window():
            logger.exception('Firestore list_docs(%s) failed', name)
        return []

    docs = []
    for snap in snapshots:
        data = snap.to_dict() or {}
        data['id'] = snap.id
        docs.append(data)

    for key, op, value in python_filters:
        docs = [d for d in docs if _matches(d, key, op, value)]

    if order_by:
        docs.sort(
            key=lambda d: (d.get(order_by) is None, d.get(order_by) or datetime.min),
            reverse=descending,
        )

    if limit:
        docs = docs[:limit]
    return docs


# ─────────────────────── Barangay helpers ───────────────────────

def create_barangay(data):
    doc_id = create_doc('barangay', data)
    _cache_clear(_CACHE_BARANGAYS)
    return doc_id


def get_barangay(barangay_id):
    return get_doc('barangay', barangay_id)


def update_barangay(barangay_id, data):
    update_doc('barangay', barangay_id, data)
    _cache_clear(_CACHE_BARANGAYS)


def list_barangays(active_only=False, search='', order_by='name', descending=False):
    # The raw list is low-volatility, so memoize it briefly; ordering and
    # filtering vary per caller, so those are re-applied in Python each time.
    barangays = _cache_get(_CACHE_BARANGAYS)
    if barangays is None:
        barangays = list_docs('barangay')
        _cache_set(_CACHE_BARANGAYS, barangays)
    if order_by:
        barangays = sorted(
            barangays,
            key=lambda b: (b.get(order_by) is None, b.get(order_by) or ''),
            reverse=descending,
        )
    if active_only:
        barangays = [b for b in barangays if b.get('is_active')]
    if search:
        search = search.lower()
        barangays = [b for b in barangays
                     if search in (b.get('name') or '').lower()
                     or search in (b.get('address') or '').lower()]
    return barangays


# ───────────────────────── User helpers ─────────────────────────

def create_user(data):
    return create_doc('user', data)


def get_user(user_id):
    return get_doc('user', user_id)


def get_user_by_username(username):
    users = list_docs('user', filters=[('username', '==', username)])
    for user in users:
        if user.get('is_active'):
            return user
    # Only ever return active accounts (or a matching username that is
    # actively enabled).  Deactivated accounts must not be able to log in.
    return None


def get_user_by_email(email):
    users = list_docs('user', filters=[('email', '==', email)])
    for user in users:
        if user.get('is_active'):
            return user
    return None


def get_users_bulk(user_ids):
    """Fetch multiple users by id in a single round-trip.

    Returns a dict mapping user id -> document dict (each with 'id'), omitting
    ids that don't exist.
    """
    ids = [str(i) for i in (user_ids or []) if i]
    if not ids:
        return {}
    refs = [collection('user').document(i) for i in dict.fromkeys(ids)]

    def _fetch_all():
        return get_db().get_all(refs)

    try:
        snaps = _with_deadline(_fetch_all)
    except Exception:
        if not _in_failure_window():
            logger.exception('Firestore get_users_bulk failed for %d ids', len(ids))
        return {}
    result = {}
    for snap in snaps:
        if snap.exists:
            data = snap.to_dict() or {}
            data['id'] = snap.id
            result[snap.id] = data
    return result


def update_user(user_id, data):
    update_doc('user', user_id, data)


def list_users(filters=None, order_by='date_joined', descending=True):
    return list_docs('user', filters=filters, order_by=order_by, descending=descending)


def count_users(filters=None):
    return len(list_docs('user', filters=filters))


# ────────────────────── Document type helpers ──────────────────────

def create_document_type(data):
    doc_id = create_doc('document_type', data)
    _cache_clear(_CACHE_DOCUMENT_TYPES)
    return doc_id


def get_document_type(document_type_id):
    return get_doc('document_type', document_type_id)


def update_document_type(document_type_id, data):
    update_doc('document_type', document_type_id, data)
    _cache_clear(_CACHE_DOCUMENT_TYPES)


def delete_document_type(document_type_id):
    delete_doc('document_type', document_type_id)
    _cache_clear(_CACHE_DOCUMENT_TYPES)


def list_document_types(filters=None, order_by='name', descending=False):
    # The raw list is low-volatility; memoize it briefly and re-apply the
    # per-caller ordering and filters in Python.
    docs = _cache_get(_CACHE_DOCUMENT_TYPES)
    if docs is None:
        docs = list_docs('document_type')
        _cache_set(_CACHE_DOCUMENT_TYPES, docs)
    for key, op, value in (filters or []):
        docs = [d for d in docs if _matches(d, key, op, value)]
    if order_by:
        docs = sorted(
            docs,
            key=lambda d: (d.get(order_by) is None, d.get(order_by) or ''),
            reverse=descending,
        )
    return docs


def create_document_type_override(data):
    doc_id = create_doc('document_type_override', data)
    _cache_clear(_CACHE_DOCUMENT_TYPES)
    return doc_id


def get_document_type_override(override_id):
    return get_doc('document_type_override', override_id)


def update_document_type_override(override_id, data):
    update_doc('document_type_override', override_id, data)
    _cache_clear(_CACHE_DOCUMENT_TYPES)


def delete_document_type_override(override_id):
    delete_doc('document_type_override', override_id)
    _cache_clear(_CACHE_DOCUMENT_TYPES)


def list_document_type_overrides(filters=None, order_by='created_at', descending=True):
    return list_docs('document_type_override', filters=filters, order_by=order_by, descending=descending)


# ───────────────────── Document request helpers ─────────────────────

def create_document_request(data):
    return create_doc('document_request', data)


def get_document_request(request_id):
    return get_doc('document_request', request_id)


def update_document_request(request_id, data):
    update_doc('document_request', request_id, data)


def delete_document_request(request_id):
    delete_doc('document_request', request_id)


def list_document_requests(filters=None, order_by='created_at', descending=True):
    return list_docs('document_request', filters=filters, order_by=order_by, descending=descending)


def next_request_number():
    """Generate the next sequential request number atomically, e.g. BRG-20260812-0001.

    A per-day counter document in the ``counters`` collection is read-and-
    incremented inside a Firestore transaction so two concurrent submissions
    can never receive the same number.  If the transaction cannot complete
    after several retries, it falls back to the (rare) scan-and-increment
    approach to keep the request flowing.
    """
    today = utcnow().strftime('%Y%m%d')
    prefix = f'BRG-{today}-'
    counter_ref = collection('counter').document(f'request_number_{today}')
    db = get_db()

    @firestore.transactional
    def _increment(transaction, ref):
        snap = ref.get(transaction=transaction)
        if snap.exists:
            value = (snap.to_dict() or {}).get('value', 0) + 1
            transaction.update(ref, {'value': value})
        else:
            value = 1
            transaction.set(ref, {'value': value})
        return value

    transaction = db.transaction()
    for attempt in range(5):
        try:
            value = _with_deadline(
                lambda: _increment(transaction, counter_ref),
                timeout=FIRESTORE_TIMEOUT_SECONDS * 2,
            )
            return f'{prefix}{value:04d}'
        except Exception:
            # Conflict/transient error: give the SDK a fresh transaction and
            # retry (a new object is required after a failed transaction).
            transaction = db.transaction()

    # Last-resort fallback (extremely rare): scan the existing requests for
    # today and pick the next number.  This mirrors the original logic.
    requests = list_docs('document_request')
    last_num = 0
    for req in requests:
        number = req.get('request_number') or ''
        if number.startswith(prefix):
            try:
                last_num = max(last_num, int(number.split('-')[-1]))
            except ValueError:
                continue
    return f'{prefix}{last_num + 1:04d}'


# ─────────────────── Document request item helpers ───────────────────

def create_document_request_item(data):
    return create_doc('document_request_item', data)


def get_document_request_item(item_id):
    return get_doc('document_request_item', item_id)


def update_document_request_item(item_id, data):
    update_doc('document_request_item', item_id, data)


def delete_document_request_item(item_id):
    delete_doc('document_request_item', item_id)


def list_document_request_items(filters=None, order_by='created_at'):
    return list_docs('document_request_item', filters=filters, order_by=order_by)


# ─────────────────────── Notification helpers ───────────────────────

@_outage_safe(default=None)
def create_notification(data):
    return create_doc('notification', data)


def get_notification(notification_id):
    return get_doc('notification', notification_id)


def update_notification(notification_id, data):
    update_doc('notification', notification_id, data)


def list_notifications(filters=None, order_by='created_at', descending=True, limit=None):
    _cleanup_expired_notifications()
    return list_docs('notification', filters=filters, order_by=order_by, descending=descending, limit=limit)


def delete_expired_notifications():
    """Delete notifications older than NOTIFICATION_TTL_DAYS.

    Uses the stored ``expires_at`` timestamp when present; falls back to
    ``created_at + TTL`` for records created before ``expires_at`` existed.
    Returns the number of notifications deleted.

    Best-effort by design: a Firestore outage or a single failing delete is
    logged and ignored so it can never break the notification read path.
    """
    now = utcnow()
    fallback_cutoff = now - timedelta(days=NOTIFICATION_TTL_DAYS)
    deleted = 0
    for notif in list_docs('notification'):
        expires_at = notif.get('expires_at')
        if expires_at is None:
            created_at = notif.get('created_at')
            if created_at is None or created_at >= fallback_cutoff:
                continue
        elif expires_at >= now:
            continue
        try:
            delete_doc('notification', notif['id'])
            deleted += 1
        except Exception:
            logger.exception('Failed to delete expired notification %s', notif.get('id'))
    return deleted


def _cleanup_expired_notifications():
    """Run the expired-notification purge at most once per interval."""
    global _last_notification_cleanup
    now = utcnow()
    if _last_notification_cleanup is not None and (now - _last_notification_cleanup) < _NOTIFICATION_CLEANUP_INTERVAL:
        return
    _last_notification_cleanup = now
    delete_expired_notifications()


# ─────────────────────── Activity log helpers ───────────────────────

@_outage_safe(default=None)
def create_activity_log(data):
    return create_doc('activity_log', data)


def list_activity_logs(filters=None, order_by='created_at', descending=True, limit=None):
    return list_docs('activity_log', filters=filters, order_by=order_by, descending=descending, limit=limit)


# ─────────────────────── Announcement helpers ───────────────────────

def create_announcement(data):
    return create_doc('announcement', data)


def get_announcement(announcement_id):
    return get_doc('announcement', announcement_id)


def update_announcement(announcement_id, data):
    update_doc('announcement', announcement_id, data)


def delete_announcement(announcement_id):
    delete_doc('announcement', announcement_id)


def list_announcements(filters=None, order_by='published_at', descending=True, limit=None):
    return list_docs('announcement', filters=filters, order_by=order_by, descending=descending, limit=limit)


# ────────────────────── Login attempt / lockout ──────────────────────

@_outage_safe(default=None)
def get_login_attempt(key):
    """Return the (possibly absent) login-attempt record for *key*.

    Records whose lockout window has already elapsed are removed so stale
    entries do not accumulate indefinitely.
    """
    attempts = list_docs('login_attempt', filters=[('key', '==', key)])
    if not attempts:
        return None
    record = attempts[0]
    if (
        record.get('count', 0) >= MAX_LOGIN_ATTEMPTS
        and record.get('locked_until')
        and record['locked_until'] <= utcnow()
    ):
        delete_doc('login_attempt', record['id'])
        return None
    return record


def _login_lockout_time():
    return timedelta(minutes=LOGIN_LOCKOUT_MINUTES)


@_outage_safe(default=False)
def is_login_locked(key):
    """True if *key* is currently locked out from failed login attempts."""
    record = get_login_attempt(key)
    if not record:
        return False
    if record.get('count', 0) < MAX_LOGIN_ATTEMPTS:
        return False
    locked_until = record.get('locked_until')
    if not locked_until:
        return False
    return locked_until > utcnow()


@_outage_safe(default=MAX_LOGIN_ATTEMPTS)
def login_attempts_remaining(key):
    """Return the number of attempts left before lockout, or None if locked."""
    record = get_login_attempt(key)
    if not record:
        return MAX_LOGIN_ATTEMPTS
    count = record.get('count', 0)
    remaining = MAX_LOGIN_ATTEMPTS - count
    if remaining <= 0 and is_login_locked(key):
        return None
    return max(remaining, 0)


@_outage_safe(default=None)
def record_failed_login(key):
    """Increment the failed-login counter for *key*; lock it when the cap is hit."""
    record = get_login_attempt(key)
    count = (record.get('count', 0) if record else 0) + 1
    data = {
        'key': key,
        'count': count,
        'last_attempt_at': utcnow(),
        'locked_until': utcnow() + _login_lockout_time() if count >= MAX_LOGIN_ATTEMPTS else None,
    }
    if record:
        update_doc('login_attempt', record['id'], data)
    else:
        create_doc('login_attempt', data)
    return count


@_outage_safe(default=None)
def clear_failed_logins(key):
    """Reset the failed-login counter for *key* (e.g. on a successful login)."""
    record = get_login_attempt(key)
    if record:
        delete_doc('login_attempt', record['id'])


# ─────────────────────── Login OTP helpers ───────────────────────

@_outage_safe(default=None)
def create_otp(user_id, code):
    """Store a login OTP for *user_id*, replacing any previous one.

    Only a single pending OTP is kept per user at a time so an old code
    cannot be replayed after a resend.  Returns the OTP document id.
    """
    delete_otp(user_id)
    now = utcnow()
    data = {
        'user_id': str(user_id),
        'code': str(code),
        'created_at': now,
        'expires_at': now + timedelta(minutes=LOGIN_OTP_TTL_MINUTES),
        'attempts': 0,
    }
    return create_doc('otp', data)


@_outage_safe(default=None)
def get_pending_otp(user_id):
    """Return the active (unexpired) OTP record for *user_id*, or None."""
    docs = list_docs('otp', filters=[('user_id', '==', str(user_id))])
    if not docs:
        return None
    record = docs[0]
    expires_at = record.get('expires_at')
    if expires_at and expires_at <= utcnow():
        delete_doc('otp', record['id'])
        return None
    return record


@_outage_safe(default=False)
def verify_otp(user_id, code):
    """Validate *code* against the pending OTP for *user_id*.

    Deletes the OTP record on a successful match and returns True.  Failed
    attempts are counted on the record; once MAX_OTP_ATTEMPTS is reached the
    record is invalidated (forcing a fresh OTP from the login page).
    """
    record = get_pending_otp(user_id)
    if not record:
        return False
    if str(record.get('code')) == str(code):
        delete_doc('otp', record['id'])
        return True
    attempts = int(record.get('attempts', 0)) + 1
    if attempts >= MAX_OTP_ATTEMPTS:
        delete_doc('otp', record['id'])
    else:
        update_doc('otp', record['id'], {'attempts': attempts})
    return False


@_outage_safe(default=None)
def delete_otp(user_id):
    """Delete any pending OTP record for *user_id*."""
    for record in list_docs('otp', filters=[('user_id', '==', str(user_id))]):
        delete_doc('otp', record['id'])
