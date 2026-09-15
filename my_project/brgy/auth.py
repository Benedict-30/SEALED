"""
Firestore-backed authentication for Django.

Django's session framework is kept (cookie-based), but users live in
Firestore, so a custom authentication backend supplies authenticate() and
get_user().  The plain login/logout helpers below set the same session keys
Django's auth framework uses, so decorators such as @login_required keep
working unchanged.
"""
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password

from . import firestore_db
from .models import CustomUser

BACKEND_PATH = 'brgy.auth.FirestoreBackend'


class FirestoreBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        data = firestore_db.get_user_by_username(username or '')
        if not data:
            return None
        user = CustomUser(data)
        # Refuse to authenticate deactivated accounts.
        if not user.is_active:
            return None
        if not check_password(password or '', user.password or ''):
            return None
        user.backend = BACKEND_PATH
        return user

    def get_user(self, user_id):
        data = firestore_db.get_user(user_id)
        if not data:
            return None
        user = CustomUser(data)
        if not user.is_active:
            return None
        return user


def login_user(request, user):
    """Log a Firestore-backed user into the current session."""
    # Rotate the session key on login to prevent session fixation: ensure any
    # cookie set by an attacker before login cannot be used to hijack the
    # newly-authenticated session.
    request.session.cycle_key()
    user.backend = BACKEND_PATH
    request.session[SESSION_KEY] = str(user.pk)
    request.session[BACKEND_SESSION_KEY] = BACKEND_PATH
    request.session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    request.session['_auth_user_hash_verified'] = True
    request._cached_user = user


def logout_user(request):
    """Clear the current session and unset request.user."""
    from django.contrib.auth.models import AnonymousUser
    request.session.flush()
    request._cached_user = AnonymousUser()
