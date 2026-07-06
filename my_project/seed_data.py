"""
Run this after migrations to seed initial data:
    python manage.py shell < seed_data.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_project.settings')
django.setup()

from brgy.models import Barangay, DocumentType, CustomUser

# Create barangays
brgy1, _ = Barangay.objects.get_or_create(
    name='Barangay San Isidro',
    defaults={
        'address': 'San Isidro, Quezon City, Metro Manila',
        'contact_number': '(02) 1234-5678',
        'email': 'sanisidro.brgy@example.com',
        'chairman_name': 'Juan Dela Cruz',
        'officials': {
            'captain': 'Juan Dela Cruz',
            'kagawad_1': 'Maria Santos',
            'kagawad_2': 'Pedro Reyes',
            'secretary': 'Ana Lim',
            'treasurer': 'Rosa Garcia',
        }
    }
)

brgy2, _ = Barangay.objects.get_or_create(
    name='Barangay Poblacion',
    defaults={
        'address': 'Poblacion, Makati City, Metro Manila',
        'contact_number': '(02) 8765-4321',
        'email': 'poblacion.brgy@example.com',
        'chairman_name': 'Ricardo Mendoza',
        'officials': {
            'captain': 'Ricardo Mendoza',
            'kagawad_1': 'Carmen Aquino',
            'kagawad_2': 'Jose Villanueva',
            'secretary': 'Grace Torres',
            'treasurer': 'Mark Nakpil',
        }
    }
)

# Create document types for each barangay
doc_types = [
    ('Barangay Clearance', 'A certificate of clearance issued by the barangay confirming that the resident has no pending cases or records.', 'Valid ID\nCommunity Tax Certificate\n1x1 Photo', 0),
    ('Certificate of Residency', 'A document certifying that the person is a bona fide resident of the barangay.', 'Valid ID\nAny proof of address', 0),
    ('Certificate of Indigency', 'A certificate issued to residents who are financially incapable, often required for social services.', 'Valid ID\nInterview with social worker', 0),
    ('Barangay Business Permit', 'A permit allowing businesses to operate within the barangay jurisdiction.', 'DTI/SEC Registration\nLease Contract\nValid ID\n2x2 Photo', 150.00),
    ('Barangay ID', 'An official identification card issued to barangay residents.', 'Valid ID\n1x1 Photo (2 pcs)\nProof of residency', 50.00),
]

for brgy in [brgy1, brgy2]:
    for name, desc, reqs, fee in doc_types:
        DocumentType.objects.get_or_create(
            name=name,
            barangay=brgy,
            defaults={
                'description': desc,
                'requirements': reqs,
                'fee': fee,
            }
        )

# Create staff accounts for each barangay
staff_data = [
    ('Maria', 'Santos', 'maria.santos@sanisidro.brgy', brgy1),
    ('Pedro', 'Reyes', 'pedro.reyes@sanisidro.brgy', brgy1),
    ('Carmen', 'Aquino', 'carmen.aquino@poblacion.brgy', brgy2),
    ('Jose', 'Villanueva', 'jose.villanueva@poblacion.brgy', brgy2),
]

for first, last, email, brgy in staff_data:
    username = email.split('@')[0]
    staff, created = CustomUser.objects.get_or_create(
        username=username,
        defaults={
            'first_name': first,
            'last_name': last,
            'email': email,
            'role': 'staff',
            'barangay': brgy,
            'verification_status': 'approved',
            'is_active': True,
        }
    )
    if created:
        staff.set_password('Staff@123')
        staff.save()

# Ensure the superuser is set as admin
superuser = CustomUser.objects.filter(is_superuser=True).first()
if superuser and superuser.role != 'admin':
    superuser.role = 'admin'
    superuser.verification_status = 'approved'
    superuser.save()

print('Seed data created successfully!')
print(f'Barangays: {Barangay.objects.count()}')
print(f'Document Types: {DocumentType.objects.count()}')
print(f'Staff Accounts: {CustomUser.objects.filter(role="staff").count()}')
print('\nStaff login credentials: username = email prefix, password = Staff@123')
print('Example: maria.santos@sanisidro.brgy / Staff@123')