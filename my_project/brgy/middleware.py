"""Replaces django.contrib.auth's AuthenticationMiddleware.

Django's stock middleware resolves the user through the ORM-backed
get_user_model(), which cannot work here because users live in Firestore.
This middleware resolves the session's user id through the Firestore backend
and exposes it as request.user, so login_required / templates keep working.
"""
from django.contrib.auth.models import AnonymousUser
from django.utils.functional import SimpleLazyObject

from .auth import FirestoreBackend


def _get_user(request):
    user_id = request.session.get('_auth_user_id')
    if not user_id:
        return AnonymousUser()
    user = FirestoreBackend().get_user(user_id)
    return user or AnonymousUser()


class FirestoreAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleLazyObject(lambda: _get_user(request))
        return self.get_response(request)
