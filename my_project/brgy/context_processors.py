from django.conf import settings

from . import firestore_db
from .models import Notification


def brgy_context(request):
    context = {'MEDIA_URL': settings.MEDIA_URL}
    if request.user.is_authenticated:
        notifications = firestore_db.list_notifications(
            filters=[('user_id', '==', request.user.pk)],
            order_by='created_at',
            descending=True,
        )
        unread_count = sum(1 for n in notifications if not n.get('is_read'))
        context['unread_notification_count'] = unread_count
        context['recent_notifications'] = [Notification(n) for n in notifications[:5]]
    return context
