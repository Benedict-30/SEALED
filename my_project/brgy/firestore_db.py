"""
Firestore data access layer.

All persistence for the barangay document system goes through Cloud
Firestore using the Firebase Admin SDK. This module replaces the Django ORM
that previously backed the SQLite database.

Queries intentionally avoid composite Firestore indexes (which must be
created manually in the console). Data is fetched with the auto-indexed
single-field equality operators where useful, and any remaining filtering and
sorting happens in Python. This is fine for a barangay-scale application.
"""
import uuid
from datetime import date, datetime, time, timezone

from firebase_admin import firestore

_COLLECTION_NAMES = {
    'barangay': 'barangays',
    'user': 'users',
    'document_type': 'document_types',
    'document_request': 'document_requests',
    'document_request_item': 'document_request_items',
    'notification': 'notifications',
    'activity_log': 'activity_logs',
}


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
    collection(name).document(doc_id).set(_to_firestore(data))
    return doc_id


def update_doc(name, doc_id, data):
    """Merge updates into an existing document."""
    data = dict(data)
    data['updated_at'] = utcnow()
    collection(name).document(str(doc_id)).set(_to_firestore(data), merge=True)


def delete_doc(name, doc_id):
    collection(name).document(str(doc_id)).delete()


def get_doc(name, doc_id):
    """Return a document dict (with 'id') or None."""
    snap = collection(name).document(str(doc_id)).get()
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

    Filters are applied in Python to avoid requiring composite Firestore
    indexes; sorting also happens in Python.
    """
    docs = []
    for snap in collection(name).stream():
        data = snap.to_dict() or {}
        data['id'] = snap.id
        docs.append(data)

    for key, op, value in (filters or []):
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
    return create_doc('barangay', data)


def get_barangay(barangay_id):
    return get_doc('barangay', barangay_id)


def update_barangay(barangay_id, data):
    update_doc('barangay', barangay_id, data)


def list_barangays(active_only=False, search='', order_by='name', descending=False):
    barangays = list_docs('barangay', order_by=order_by, descending=descending)
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
    if not users:
        return None
    for user in users:
        if user.get('is_active'):
            return user
    return users[0]


def update_user(user_id, data):
    update_doc('user', user_id, data)


def list_users(filters=None, order_by='date_joined', descending=True):
    return list_docs('user', filters=filters, order_by=order_by, descending=descending)


def count_users(filters=None):
    return len(list_docs('user', filters=filters))


# ────────────────────── Document type helpers ──────────────────────

def create_document_type(data):
    return create_doc('document_type', data)


def get_document_type(document_type_id):
    return get_doc('document_type', document_type_id)


def update_document_type(document_type_id, data):
    update_doc('document_type', document_type_id, data)


def delete_document_type(document_type_id):
    delete_doc('document_type', document_type_id)


def list_document_types(filters=None, order_by='name', descending=False):
    return list_docs('document_type', filters=filters, order_by=order_by, descending=descending)


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
    """Generate the next sequential request number, e.g. BRG-20260812-0001."""
    today = utcnow().strftime('%Y%m%d')
    prefix = f'BRG-{today}-'
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


def delete_document_request_item(item_id):
    delete_doc('document_request_item', item_id)


def list_document_request_items(filters=None, order_by='created_at'):
    return list_docs('document_request_item', filters=filters, order_by=order_by)


# ─────────────────────── Notification helpers ───────────────────────

def create_notification(data):
    return create_doc('notification', data)


def get_notification(notification_id):
    return get_doc('notification', notification_id)


def update_notification(notification_id, data):
    update_doc('notification', notification_id, data)


def list_notifications(filters=None, order_by='created_at', descending=True, limit=None):
    return list_docs('notification', filters=filters, order_by=order_by, descending=descending, limit=limit)


# ─────────────────────── Activity log helpers ───────────────────────

def create_activity_log(data):
    return create_doc('activity_log', data)


def list_activity_logs(filters=None, order_by='created_at', descending=True):
    return list_docs('activity_log', filters=filters, order_by=order_by, descending=descending)
