import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_project.settings')
django.setup()

from brgy.models import CustomUser

# Ensure any existing test user is removed
CustomUser.objects.filter(username="test").delete()

# Create a new test user
u = CustomUser(username="test", email="test@example.com")
u.set_password("testpass")
u.is_active = True
u.verification_status = "approved"
u.save()

print("Created test user")