"""Views split by role. Re-exports every view so ``from . import views`` still works."""
from .common import (
    dashboard_redirect, home_page, login_view, logout_view, mark_all_notifications_read,
    mark_notification_read, register_view,
)
from .resident import (
    cancel_request, notifications_view, request_document, request_history,
    resident_dashboard, resident_profile, submit_bulk_request, track_request,
)
from .staff import (
    approve_resident, manage_requests, print_document, reject_request, reject_resident,
    staff_dashboard, staff_delete_document_type, staff_edit_document_type,
    staff_manage_document_types, staff_reports, update_request_status, verify_residents,
)
from .admin import (
    activity_logs, admin_dashboard, change_barangay_logo, delete_document_type,
    edit_barangay, edit_document_type, edit_staff, manage_barangays,
    manage_document_types, manage_staff, toggle_staff_active,
)
