import os
import firebase_admin
from firebase_admin import credentials

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    cred_path = os.path.join(os.path.dirname(__file__), 'firebase_credentials.json')
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

# Now import firestore_db to fetch user docs
from brgy import firestore_db

# Get first 5 user documents
users = firestore_db.list_docs('user')[:5]

for doc in users:
    print('User ID:', doc.get('id'))
    print('  username:', doc.get('username'))
    print('  password field present:', 'password' in doc)
    print('  password value:', doc.get('password'))
    print('  is_active field present:', 'is_active' in doc)
    if 'is_active' in doc:
        print('  is_active value:', doc.get('is_active'))
    print('  created_at:', doc.get('created_at'))
    print('---')