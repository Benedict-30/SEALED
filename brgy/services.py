"""Shared helpers for the brgy views (business logic + small view utilities)."""
import os

from django.http import Http404

from . import firestore_db
from .models import (
    DocumentRequest, DocumentRequestItem,
    get_barangay, get_document_request, get_document_type, get_request_items,
    get_user,
)


def log_activity(user, action, details='', request=None):
    ip = request.META.get('REMOTE_ADDR') if request else None
    firestore_db.create_activity_log({
        'user_id': user.pk if user else None,
        'action': action,
        'details': details,
        'ip_address': ip,
    })


def notify(user_id, title, message, link=''):
    firestore_db.create_notification({
        'user_id': user_id,
        'title': title,
        'message': message,
        'link': link,
        'is_read': False,
    })


def staff_of_barangay(barangay_id):
    users = firestore_db.list_users()
    return [
        u for u in users
        if u.get('role') == 'staff' and u.get('barangay_id') == barangay_id and u.get('is_active')
    ]


def requests_for_barangay(barangay_id):
    """Document requests whose resident belongs to the given barangay."""
    requests = firestore_db.list_document_requests()
    residents = {}
    for req in requests:
        resident_id = req.get('resident_id')
        if resident_id and resident_id not in residents:
            residents[resident_id] = firestore_db.get_user(resident_id)
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


def _request_or_404(pk):
    req = get_document_request(pk)
    if not req:
        raise Http404
    return req


def _item_or_404(pk):
    item = firestore_db.get_document_request_item(pk)
    if not item:
        raise Http404
    return DocumentRequestItem(item)


def _delete_template_file(doc_type):
    path = getattr(doc_type.template_file, 'path', '')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _save_uploaded_file(uploaded_file, subdir=''):
    """Helper to save an uploaded file to media/storage and return its name path."""
    if not uploaded_file:
        return ''
    from django.core.files.storage import default_storage
    name = os.path.join(subdir, uploaded_file.name) if subdir else uploaded_file.name
    path = default_storage.save(name, uploaded_file)
    return path
