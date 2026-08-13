import os
import firebase_admin
from firebase_admin import credentials

# Initialize Firebase
if not firebase_admin._apps:
    cred_path = os.path.join(os.path.dirname(__file__), 'firebase_credentials.json')
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

from brgy import firestore_db

# Fetch all user docs with id and data
users = firestore_db.list_docs('user')
print(f'Found {len(users)} users')
updated = 0
for doc in users:
    doc_id = doc.get('id')
    if not doc_id:
        continue
    # Check if 'is_active' field exists
    if 'is_active' not in doc:
        print(f'Updating user {doc_id} to add is_active=True')
        firestore_db.update_doc('user', doc_id, {'is_active': True})
        updated += 1
print(f'Updated {updated} users')