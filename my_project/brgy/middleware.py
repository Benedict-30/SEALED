"""Replaces django.contrib.auth's AuthenticationMiddleware.

Django's stock middleware resolves the user through the ORM-backed
get_user_model(), which cannot work here because users live in Firestore.
This middleware resolves the session's user id through the Firestore backend
and exposes it as request.user, so login_required / templates keep working.
"""
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.models import AnonymousUser
from django.utils.functional import SimpleLazyObject

from .auth import FirestoreBackend


def _get_user(request):
    user_id = request.session.get(SESSION_KEY)
    if not user_id:
        return AnonymousUser()
    user = FirestoreBackend().get_user(user_id)
    if user is None:
        # Account was deactivated or deleted; discard the stale session.
        request.session.flush()
        return AnonymousUser()

    # Session hash is invalidated whenever the user's password changes.  If
    # the stored hash does not match, the session belongs to a previous
    # password state and must not be trusted (e.g. it may predate a password
    # reset), so log the user out.
    session_hash = request.session.get(HASH_SESSION_KEY)
    if not session_hash or session_hash != user.get_session_auth_hash():
        request.session.flush()
        return AnonymousUser()

    return user


class FirestoreAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleLazyObject(lambda: _get_user(request))
        return self.get_response(request)
