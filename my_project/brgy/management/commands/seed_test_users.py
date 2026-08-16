"""
Seed test data so every role in the system can be exercised.

Creates (idempotently):
  - one active test barangay
  - one admin, one staff, one approved resident, one pending resident
  - a few document types for the test barangay

Usage:
    python manage.py seed_test_users
"""
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from brgy import firestore_db

DEFAULT_PASSWORD = 'Test@123'

USERS = [
    {
        'key': 'admin',
        'username': 'admin',
        'first_name': 'Test',
        'last_name': 'Admin',
        'email': 'admin@test.com',
        'role': 'admin',
        'verification_status': 'approved',
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'key': 'staff',
        'username': 'staff',
        'first_name': 'Test',
        'last_name': 'Staff',
        'email': 'staff@test.com',
        'role': 'staff',
        'verification_status': 'approved',
        'is_staff': True,
        'is_superuser': False,
    },
    {
        'key': 'resident',
        'username': 'resident',
        'first_name': 'Test',
        'last_name': 'Resident',
        'email': 'resident@test.com',
        'role': 'resident',
        'verification_status': 'approved',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'key': 'resident_pending',
        'username': 'resident_pending',
        'first_name': 'Pending',
        'last_name': 'Resident',
        'email': 'pending@test.com',
        'role': 'resident',
        'verification_status': 'pending',
        'is_staff': False,
        'is_superuser': False,
    },
]

DOCUMENT_TYPES = [
    {'name': 'Barangay Clearance', 'fee': 100.0, 'requirements': 'Valid ID'},
    {'name': 'Barangay ID', 'fee': 150.0, 'requirements': '2x2 photo\nValid ID'},
    {'name': 'Certificate of Indigency', 'fee': 0.0, 'requirements': 'Valid ID'},
]


def _get_or_create_barangay():
    existing = [b for b in firestore_db.list_barangays() if b.get('is_active')]
    if existing:
        return existing[0]['id'], existing[0].get('name', '')
    data = {
        'name': 'Barangay Test',
        'chairman_name': 'Chairman Test',
        'address': '123 Test Street, Test City',
        'contact_number': '09170000000',
        'email': 'barangay@test.com',
        'theme_color': '#059669',
        'is_active': True,
        'officials': {},
    }
    barangay_id = firestore_db.create_barangay(data)
    return barangay_id, data['name']


def _user_exists(username):
    return firestore_db.get_user_by_username(username) is not None


def _seed_user(spec, barangay_id, password):
    if _user_exists(spec['username']):
        return False
    user_data = {
        'username': spec['username'],
        'password': make_password(password),
        'first_name': spec['first_name'],
        'middle_name': '',
        'last_name': spec['last_name'],
        'email': spec['email'],
        'role': spec['role'],
        'verification_status': spec['verification_status'],
        'is_active': True,
        'is_staff': spec['is_staff'],
        'is_superuser': spec['is_superuser'],
        'barangay_id': barangay_id,
        'address': '123 Test Street',
        'phone_number': '09170000001',
        'birth_date': None,
        'gender': 'Male',
        'civil_status': 'Single',
        'occupation': 'Tester',
        'id_type': '',
        'id_front': '',
        'id_back': '',
        'profile_picture': '',
        'rejection_reason': '',
        'date_joined': firestore_db.utcnow(),
    }
    firestore_db.create_user(user_data)
    return True


def _seed_document_types(barangay_id):
    existing = {
        dt.get('name')
        for dt in firestore_db.list_document_types()
        if dt.get('barangay_id') == barangay_id
    }
    created = []
    for spec in DOCUMENT_TYPES:
        if spec['name'] in existing:
            continue
        firestore_db.create_document_type({
            'name': spec['name'],
            'description': spec['name'],
            'requirements': spec['requirements'],
            'fee': spec['fee'],
            'is_active': True,
            'barangay_id': barangay_id,
            'template_file': '',
        })
        created.append(spec['name'])
    return created


class Command(BaseCommand):
    help = 'Create test users for every role (admin, staff, resident) plus seed data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default=DEFAULT_PASSWORD,
            help=f'Password for all test users (default: {DEFAULT_PASSWORD}).',
        )

    def handle(self, *args, **options):
        password = options['password']
        barangay_id, barangay_name = _get_or_create_barangay()

        self.stdout.write(self.style.SUCCESS(f'Barangay: {barangay_name} ({barangay_id})'))

        created = []
        for spec in USERS:
            made = _seed_user(spec, barangay_id, password)
            created.append((spec, made))

        doc_types = _seed_document_types(barangay_id)
        if doc_types:
            self.stdout.write(self.style.SUCCESS(
                f'Created document types: {", ".join(doc_types)}'
            ))

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Test credentials (username / password)'))
        for spec, made in created:
            status = 'created' if made else 'already exists'
            self.stdout.write(
                f'  {spec["username"]:<16} / {password:<12}  '
                f'-> {spec["role"]:<10} {status}'
            )
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Done. Log in at /login/ to test each role.'))
