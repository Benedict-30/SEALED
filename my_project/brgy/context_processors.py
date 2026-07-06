from .models import Notification

def brgy_context(request):
    context = {}
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        recent_notifications = Notification.objects.filter(user=request.user)[:5]
        context['unread_notification_count'] = unread_count
        context['recent_notifications'] = recent_notifications
    return context