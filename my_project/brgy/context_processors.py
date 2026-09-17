import logging

from django.conf import settings

from . import firestore_db
from .models import Notification

logger = logging.getLogger(__name__)

_SIDEBAR_MAP = {
    'resident_dashboard': 'res_dashboard',
    'request_document': 'res_request',
    'submit_bulk_request': 'res_request',
    'request_history': 'res_history',
    'track_request': 'res_history',
    'track_request_item': 'res_history',
    'cancel_request': 'res_history',
    'notifications': 'res_notifications',
    'mark_all_notifications_read': 'res_notifications',
    'mark_notification_read': 'res_notifications',
    'staff_dashboard': 'staff_dashboard',
    'staff_profile': 'staff_requests',
    'staff_notifications': 'staff_notifications',
    'verify_residents': 'staff_verify',
    'approve_resident': 'staff_verify',
    'reject_resident': 'staff_verify',
    'manage_requests': 'staff_requests',
    'update_request_status': 'staff_requests',
    'reject_request': 'staff_requests',
    'print_document': 'staff_requests',
    'staff_manage_document_types': 'staff_doctypes',
    'staff_edit_document_type': 'staff_doctypes',
    'staff_delete_document_type': 'staff_doctypes',
    'staff_reports': 'staff_reports',
    'staff_reports_export': 'staff_reports',
    'manage_announcements': 'announcements',
    'toggle_announcement': 'announcements',
    'delete_announcement': 'announcements',
    'admin_dashboard': 'admin_dashboard',
    'manage_staff': 'admin_staff',
    'edit_staff': 'admin_staff',
    'toggle_staff_active': 'admin_staff',
    'manage_barangays': 'admin_barangays',
    'edit_barangay': 'admin_barangays',
    'change_barangay_logo': 'admin_barangays',
    'manage_document_types': 'admin_doctypes',
    'edit_document_type': 'admin_doctypes',
    'delete_document_type': 'admin_doctypes',
    'activity_logs': 'admin_logs',
    'activity_logs_export': 'admin_logs',
    'admin_reports': 'admin_reports',
    'admin_reports_export': 'admin_reports',
    'admin_notifications': 'admin_notifications',
}


def brgy_context(request):
    resolver_match = getattr(request, 'resolver_match', None)
    context = {
        'MEDIA_URL': settings.MEDIA_URL,
        'sidebar_active': _SIDEBAR_MAP.get(resolver_match.url_name) if resolver_match else None,
    }
    if request.user.is_authenticated:
        if getattr(request, 'notifications_loaded', False):
            return context
        try:
            notifications = firestore_db.list_notifications(
                filters=[('user_id', '==', request.user.pk)],
                order_by='created_at',
                descending=True,
            )
        except Exception:
            logger.exception('Failed to load notifications for %s', request.user.pk)
            notifications = []
        unread_count = sum(1 for n in notifications if not n.get('is_read'))
        context['unread_notification_count'] = unread_count
        context['recent_notifications'] = [Notification(n) for n in notifications[:5]]
    return context
