"""
Firestore-backed domain objects.

These are lightweight, dict-backed wrappers around Firestore documents so the
views and templates keep working without the Django ORM. Each class mirrors
the public surface of the old Django models (field names, properties, display
helpers) so templates render unchanged.
"""
import os
from datetime import date, datetime, time, timezone

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils.crypto import salted_hmac

from . import firestore_db


class _File:
    """Mimics a FileField value (has .name, .url, .path)."""

    def __init__(self, name=''):
        self.name = name or ''

    @property
    def path(self):
        if not self.name:
            return ''
        return os.path.join(settings.MEDIA_ROOT, self.name)

    @property
    def url(self):
        if not self.name:
            return ''
        return settings.MEDIA_URL + self.name

    def __bool__(self):
        return bool(self.name)

    def __str__(self):
        return self.name


def _to_storage(value):
    """Convert Python values into Firestore-safe values."""
    if isinstance(value, _File):
        return value.name
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time.min)
    if isinstance(value, dict):
        return {k: _to_storage(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_storage(v) for v in value]
    return value


def _resolve(value):
    """Convert stored Firestore values into Python values."""
    if isinstance(value, datetime):
        from django.utils import timezone
        return timezone.localtime(value) if timezone.is_aware(value) else value
    return value


class Base:
    _collection_key = None
    _file_fields = ()

    def __init__(self, data=None, pk=None, **kwargs):
        object.__setattr__(self, '_data', dict(data or {}))
        if kwargs:
            self._data.update(kwargs)
        object.__setattr__(self, '_cache', {})
        if pk:
            self._data['id'] = pk
        for field in self._file_fields:
            value = self._data.get(field)
            if not isinstance(value, _File):
                self._data[field] = _File(value or '')

    @property
    def pk(self):
        return self._data.get('id')

    @property
    def id(self):
        return self._data.get('id')

    def __getattr__(self, name):
        data = self.__dict__['_data']
        if name in data:
            return _resolve(data[name])
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    def _cached(self, key, factory):
        if key not in self._cache:
            self._cache[key] = factory()
        return self._cache[key]

    def save(self):
        data = {k: _to_storage(v) for k, v in self._data.items() if k != 'id'}
        if self.pk:
            firestore_db.update_doc(self._collection_key, self.pk, data)
        else:
            self._data['id'] = firestore_db.create_doc(self._collection_key, data)


class Barangay(Base):
    _collection_key = 'barangay'
    _file_fields = ('logo',)

    @property
    def resident_count(self):
        return firestore_db.count_users(
            filters=[('role', '==', 'resident'), ('verification_status', '==', 'approved'),
                     ('barangay_id', '==', self.pk)]
        )

    @property
    def staff_count(self):
        return firestore_db.count_users(
            filters=[('role', '==', 'staff'), ('is_active', '==', True),
                     ('barangay_id', '==', self.pk)]
        )

    @property
    def pending_requests_count(self):
        return len(firestore_db.list_document_requests(
            filters=[('status', '==', 'pending')]
        ))

    class _BarangayQuerySet:
        def filter(self, **kwargs):
            # Convert kwargs to Firestore equality filters
            filters = [(field, '==', value) for field, value in kwargs.items()]
            docs = firestore_db.list_docs('barangay', filters=filters)
            class Dummy:
                def __iter__(self):
                    return iter(docs)
                def all(self):
                    return docs
                def __len__(self):
                    return len(docs)
                def delete(self):
                    for doc in docs:
                        firestore_db.delete_doc('barangay', doc['id'])
            return Dummy()
    objects = _BarangayQuerySet()


class CustomUser(Base):
    _collection_key = 'user'
    _file_fields = ('id_front', 'id_back', 'profile_picture')
    _meta = type('Meta', (), {'app_label': 'brgy', 'model_name': 'customuser', 'fields': {}})()

    class Role:
        choices = [
            ('resident', 'Resident'),
            ('staff', 'Staff'),
            ('admin', 'Administrator'),
        ]

    class VerificationStatus:
        choices = [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ]

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def barangay(self):
        barangay_id = self._data.get('barangay_id')
        if not barangay_id:
            return None
        return self._cached('barangay', lambda: get_barangay(barangay_id))

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def is_verified_resident(self):
        return self.role == 'resident' and self.verification_status == 'approved'

    @property
    def is_pending_resident(self):
        return self.role == 'resident' and self.verification_status == 'pending'

    @property
    def birth_date(self):
        value = self._data.get('birth_date')
        if isinstance(value, datetime):
            return value.date()
        return value

    def get_full_name(self):
        parts = [getattr(self, 'first_name', '') or '',
                 getattr(self, 'middle_name', '') or '',
                 getattr(self, 'last_name', '') or '']
        return ' '.join(p for p in parts if p).strip() or ''

    def get_short_name(self):
        return getattr(self, 'first_name', '') or getattr(self, 'username', '') or ''

    def get_role_display(self):
        role = self._data.get('role')
        for value, label in self.Role.choices:
            if value == role:
                return label
        return role or 'User'

    def get_verification_status_display(self):
        status = self._data.get('verification_status')
        for value, label in self.VerificationStatus.choices:
            if value == status:
                return label
        return status or ''

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def get_session_auth_hash(self):
        return salted_hmac('django.contrib.auth.models.AbstractBaseUser.get_session_auth_hash',
                          self.password or '').hexdigest()

    def __str__(self):
        return f'{self.display_name} ({self.get_role_display()})'


class _CustomUserQuerySet:
    def filter(self, **kwargs):
        filters = [(field, '==', value) for field, value in kwargs.items()]
        docs = firestore_db.list_docs('user', filters=filters)
        class Dummy:
            def __iter__(self):
                return iter(docs)
            def all(self):
                return docs
            def __len__(self):
                return len(docs)
            def delete(self):
                for doc in docs:
                    firestore_db.delete_doc('user', doc['id'])
        return Dummy()

print("Creating CustomUser objects")
CustomUser.objects = _CustomUserQuerySet()


class DocumentType(Base):
    _collection_key = 'document_type'
    _file_fields = ('template_file',)

    @property
    def barangay(self):
        barangay_id = self._data.get('barangay_id')
        if not barangay_id:
            return None
        return self._cached('barangay', lambda: get_barangay(barangay_id))

    @property
    def requirements_list(self):
        requirements = self.requirements or ''
        return [r.strip() for r in requirements.split('\n') if r.strip()]

    @property
    def has_template(self):
        return bool(getattr(self.template_file, 'name', ''))

    class _DocumentTypeQuerySet:
        def all(self):
            return firestore_db.list_docs('document_type')

        def filter(self, **kwargs):
            filters = [(field, '==', value) for field, value in kwargs.items()]
            docs = firestore_db.list_docs('document_type', filters=filters)
            class Dummy:
                def __iter__(self):
                    return iter(docs)
                def all(self):
                    return docs
                def __len__(self):
                    return len(docs)
                def delete(self):
                    for doc in docs:
                        firestore_db.delete_doc('document_type', doc['id'])
            return Dummy()
        
        def none(self):
            class EmptyDummy:
                def __iter__(self):
                    return iter([])
                def all(self):
                    return []
                def __len__(self):
                    return 0
            return EmptyDummy()

    objects = _DocumentTypeQuerySet()


class DocumentRequestItem(Base):
    _collection_key = 'document_request_item'

    @property
    def document_type(self):
        document_type_id = self._data.get('document_type_id')
        if not document_type_id:
            return None
        return self._cached('document_type', lambda: get_document_type(document_type_id))

    @property
    def total_fee(self):
        doc_type = self.document_type
        if not doc_type:
            return 0
        return float(doc_type.fee or 0) * int(self.quantity or 0)

    @property
    def requirement_files(self):
        return self._data.get('requirement_files') or []


class DocumentRequest(Base):
    _collection_key = 'document_request'

    class Status:
        choices = [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('ready_for_pickup', 'Ready for Pickup'),
            ('completed', 'Completed'),
            ('rejected', 'Rejected'),
        ]

    @property
    def resident(self):
        resident_id = self._data.get('resident_id')
        if not resident_id:
            return None
        return self._cached('resident', lambda: get_user(resident_id))

    @property
    def processed_by(self):
        processed_by_id = self._data.get('processed_by_id')
        if not processed_by_id:
            return None
        return self._cached('processed_by', lambda: get_user(processed_by_id))

    @property
    def barangay(self):
        return self.resident.barangay if self.resident else None

    @property
    def pickup_date(self):
        value = self._data.get('pickup_date')
        if isinstance(value, datetime):
            return value.date()
        return value

    @property
    def items(self):
        class ItemsManager:
            def __init__(self, request_obj):
                self.request_obj = request_obj

            def all(self):
                return get_request_items(self.request_obj.pk)

        return ItemsManager(self)

    @property
    def status_color(self):
        colors = {
            'pending': 'warning',
            'approved': 'info',
            'ready_for_pickup': 'success',
            'completed': 'primary',
            'rejected': 'danger',
        }
        return colors.get(self.status, 'muted')

    def get_status_display(self):
        for value, label in self.Status.choices:
            if value == self.status:
                return label
        return self.status


class Notification(Base):
    _collection_key = 'notification'

    @property
    def user(self):
        user_id = self._data.get('user_id')
        if not user_id:
            return None
        return self._cached('user', lambda: get_user(user_id))


class ActivityLog(Base):
    _collection_key = 'activity_log'

    @property
    def user(self):
        user_id = self._data.get('user_id')
        if not user_id:
            return None
        return self._cached('user', lambda: get_user(user_id))


# ──────────────────────── Conversion helpers ────────────────────────

def get_barangay(barangay_id):
    data = firestore_db.get_barangay(barangay_id)
    return Barangay(data) if data else None


def get_user(user_id):
    data = firestore_db.get_user(user_id)
    return CustomUser(data) if data else None


def get_document_type(document_type_id):
    data = firestore_db.get_document_type(document_type_id)
    return DocumentType(data) if data else None


def get_document_request(request_id):
    data = firestore_db.get_document_request(request_id)
    return DocumentRequest(data) if data else None


def get_request_items(request_id):
    docs = firestore_db.list_document_request_items(
        filters=[('request_id', '==', request_id)]
    )
    return [DocumentRequestItem(doc) for doc in docs]