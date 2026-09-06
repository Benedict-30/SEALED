r"""Offline smoke tests for the Barangay Document System.

These run WITHOUT a database or Firestore, so they are safe to execute locally
anywhere. They verify that the Django app loads, its URL routes resolve, and
the pieces added throughout the feature work (password reset, payments,
reports, announcements, pickup scheduling) exist and wire together.

Run from the my_project directory:

    ..\venv\Scripts\python.exe smoke_tests.py

Or as a unittest module:

    ..\venv\Scripts\python.exe -m unittest smoke_tests -v
"""
import os
import sys
import unittest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_project.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
django.setup()

from django.core.management import call_command
from django.urls import reverse


class AppHealthTests(unittest.TestCase):

    def test_django_check_passes(self):
        call_command('check')

    def test_views_module_imports(self):
        from brgy import views
        for name in (
            'password_reset', 'password_reset_confirm', 'resident_password_change',
            'send_user_email', '_make_reset_token', '_parse_reset_token',
        ):
            self.assertTrue(hasattr(views, name), f'views.{name} missing')

    def test_phase2_views_exist(self):
        from brgy import views
        for name in ('mark_paid',):
            self.assertTrue(hasattr(views, name), f'views.{name} missing')

    def test_phase3_views_exist(self):
        from brgy import views
        for name in ('admin_reports', 'admin_reports_export', 'activity_logs_export'):
            self.assertTrue(hasattr(views, name), f'views.{name} missing')

    def test_phase4_views_exist(self):
        from brgy import views
        self.assertTrue(hasattr(views, 'toggle_resident_active'))

    def test_phase5_views_exist(self):
        from brgy import views
        for name in ('manage_announcements', 'toggle_announcement', 'delete_announcement'):
            self.assertTrue(hasattr(views, name), f'views.{name} missing')

    def test_pickup_scheduling_helpers(self):
        from brgy import views
        from brgy.models import DocumentRequest
        self.assertTrue(hasattr(views, 'mark_ready_for_pickup'))
        self.assertTrue(hasattr(DocumentRequest, 'PickupSlot'))
        self.assertEqual(
            dict(DocumentRequest.PickupSlot.choices),
            {
                'morning': 'Morning (8:00 AM - 12:00 NN)',
                'afternoon': 'Afternoon (12:00 NN - 5:00 PM)',
                'evening': 'Evening (5:00 PM - 8:00 PM)',
                'any': 'Any Time',
            },
        )

    def test_forms_exist(self):
        from brgy import forms
        for name in (
            'RequestPasswordResetForm', 'SetNewPasswordForm', 'MarkPaymentForm',
            'AnnouncementForm',
        ):
            self.assertTrue(hasattr(forms, name), f'forms.{name} missing')

    def test_model_wrappers(self):
        from brgy.models import Announcement, DocumentRequest
        self.assertTrue(hasattr(DocumentRequest, 'PaymentStatus'))
        self.assertTrue(hasattr(DocumentRequest, 'PickupSlot'))
        req = DocumentRequest({'status': 'pending', 'payment_status': 'unpaid'})
        self.assertEqual(req.get_payment_status_display(), 'Unpaid')
        self.assertFalse(req.is_paid)
        ann = Announcement({'title': 'Test', 'is_published': True})
        self.assertTrue(ann.is_published)
        self.assertTrue(ann.is_global)

    UID = '11111111-1111-1111-1111-111111111111'

    def test_urls_resolve(self):
        names = [
            'password_reset', 'resident_password_change',
            'activity_logs_export', 'admin_reports', 'admin_reports_export',
            'manage_announcements',
            ('toggle_staff_active', {'pk': self.UID}),
            ('mark_paid', {'pk': self.UID}),
            ('mark_ready_for_pickup', {'pk': self.UID}),
            ('toggle_resident_active', {'pk': self.UID}),
            ('toggle_announcement', {'pk': self.UID}),
            ('delete_announcement', {'pk': self.UID}),
        ]
        for entry in names:
            name, kwargs = entry if isinstance(entry, tuple) else (entry, None)
            with self.subTest(url=name):
                reverse(name, kwargs=kwargs) if kwargs else reverse(name)

    def test_status_transition_signature(self):
        from inspect import signature
        from brgy.views import _apply_status_transition
        params = signature(_apply_status_transition).parameters
        self.assertIn('pickup_date', params)
        self.assertIn('pickup_slot', params)

    def test_status_workflow_next_transitions(self):
        from brgy.views import _next_statuses, _status_choices_for
        self.assertEqual(_next_statuses('pending'), ['approved', 'rejected'])
        self.assertEqual(_next_statuses('approved'), ['printed', 'rejected'])
        self.assertEqual(_next_statuses('printed'), ['ready_for_pickup', 'rejected'])
        self.assertEqual(_next_statuses('ready_for_pickup'), ['completed', 'rejected'])
        self.assertEqual(_next_statuses('completed'), [])
        self.assertEqual(_next_statuses('rejected'), [])
        choices = _status_choices_for('pending')
        self.assertEqual([c for c, _ in choices], ['approved', 'rejected'])
        self.assertEqual(dict(choices)['approved'], 'Approved')

    def test_cancel_reject_views_exist(self):
        from brgy import views
        for name in (
            'cancel_request', 'reject_request', 'reject_resident',
            'toggle_resident_active', 'mark_printed', 'print_document',
            'update_request_status', 'mark_ready_for_pickup', 'mark_paid',
        ):
            self.assertTrue(hasattr(views, name), f'views.{name} missing')

    def test_document_type_management_views_exist(self):
        from brgy import views
        for name in (
            'staff_manage_document_types', 'staff_edit_document_type',
            'staff_delete_document_type', 'staff_edit_global_type',
            'manage_document_types', 'edit_document_type', 'delete_document_type',
        ):
            self.assertTrue(hasattr(views, name), f'views.{name} missing')

    def test_admin_staff_barangay_views_exist(self):
        from brgy import views
        for name in (
            'manage_staff', 'edit_staff', 'toggle_staff_active', 'reset_staff_password',
            'manage_barangays', 'edit_barangay', 'change_barangay_logo',
        ):
            self.assertTrue(hasattr(views, name), f'views.{name} missing')

    def test_misc_views_exist(self):
        from brgy import views
        for name in (
            'verify_document_view', 'unread_notification_count',
            'mark_all_notifications_read', 'track_request', 'notify_admins',
            'requests_for_barangay', 'notifications_url_name', 'staff_of_barangay',
        ):
            self.assertTrue(hasattr(views, name), f'views.{name} missing')

    def test_all_forms_exist(self):
        from brgy import forms
        for name in (
            'CustomAuthForm', 'ResidentRegistrationForm', 'StaffCreationForm',
            'BarangayForm', 'DocumentTypeForm', 'GlobalTypeOverrideForm',
            'RejectForm', 'UpdateStatusForm', 'StaffProfileForm', 'ChangePasswordForm',
            'RequestPasswordResetForm', 'SetNewPasswordForm', 'MarkPaymentForm',
            'AnnouncementForm',
        ):
            self.assertTrue(hasattr(forms, name), f'forms.{name} missing')

    def test_urls_resolve_every_view(self):
        uid = self.UID
        names = [
            'home', 'services', 'about', 'login', 'register', 'logout',
            'password_reset', 'dashboard', 'verify_document',
            'resident_dashboard', 'profile', 'resident_password_change',
            'request_document', 'submit_bulk_request', 'request_history',
            'notifications', 'mark_all_notifications_read',
            'unread_notification_count', 'staff_dashboard', 'staff_profile',
            'staff_notifications', 'verify_residents', 'manage_requests',
            'staff_reports', 'staff_reports_export', 'manage_announcements',
            'staff_manage_document_types', 'admin_dashboard', 'manage_staff',
            'manage_barangays', 'manage_document_types', 'activity_logs',
            'activity_logs_export', 'admin_reports', 'admin_reports_export',
            'admin_notifications',
            ('document_preview', {'pk': uid}),
            ('mark_notification_read', {'pk': uid}),
            ('cancel_request', {'pk': uid}),
            ('track_request', {'pk': uid}),
            ('track_request_item', {'pk': uid, 'item_pk': uid}),
            ('approve_resident', {'pk': uid}),
            ('reject_resident', {'pk': uid}),
            ('toggle_resident_active', {'pk': uid}),
            ('update_request_status', {'pk': uid}),
            ('mark_ready_for_pickup', {'pk': uid}),
            ('mark_paid', {'pk': uid}),
            ('reject_request', {'pk': uid}),
            ('toggle_announcement', {'pk': uid}),
            ('delete_announcement', {'pk': uid}),
            ('staff_edit_document_type', {'pk': uid}),
            ('staff_edit_global_type', {'pk': uid}),
            ('staff_delete_document_type', {'pk': uid}),
            ('edit_staff', {'pk': uid}),
            ('toggle_staff_active', {'pk': uid}),
            ('reset_staff_password', {'pk': uid}),
            ('edit_barangay', {'pk': uid}),
            ('change_barangay_logo', {'pk': uid}),
            ('edit_document_type', {'pk': uid}),
            ('delete_document_type', {'pk': uid}),
            ('password_reset_confirm', {'token': 'sometoken'}),
            ('print_document', {'req_pk': uid, 'item_pk': uid}),
            ('mark_printed', {'req_pk': uid, 'item_pk': uid}),
        ]
        for entry in names:
            name, kwargs = entry if isinstance(entry, tuple) else (entry, None)
            with self.subTest(url=name):
                reverse(name, kwargs=kwargs) if kwargs else reverse(name)

    def test_firestore_data_layer_surface(self):
        from brgy import firestore_db as db
        for name in (
            'next_request_number', 'list_document_requests', 'get_document_request',
            'create_document_request', 'update_document_request', 'delete_document_request',
            'list_document_request_items', 'get_document_request_item',
            'create_document_request_item', 'update_document_request_item',
            'delete_document_request_item',
            'create_notification', 'get_notification', 'update_notification',
            'list_notifications', 'delete_expired_notifications',
            'create_announcement', 'get_announcement', 'update_announcement',
            'delete_announcement', 'list_announcements',
            'create_activity_log', 'list_activity_logs',
            'get_login_attempt', 'is_login_locked', 'record_failed_login',
            'login_attempts_remaining', 'clear_failed_logins',
            'get_users_bulk', 'count_users', 'list_document_type_overrides',
            'create_document_type_override', 'delete_document_type_override',
        ):
            self.assertTrue(hasattr(db, name), f'firestore_db.{name} missing')

    def test_reset_token_round_trip(self):
        from unittest.mock import patch
        import brgy.views as views
        from brgy.models import CustomUser
        from django.contrib.auth.hashers import make_password

        uid = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        user = CustomUser({'id': uid, 'password': make_password('testpass123')})
        token = views._make_reset_token(user)

        with patch.object(views, 'get_user', return_value=user):
            parsed = views._parse_reset_token(token)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed.pk, uid)

        changed = CustomUser({'id': uid, 'password': make_password('rotatedpass')})
        with patch.object(views, 'get_user', return_value=changed):
            self.assertIsNone(views._parse_reset_token(token))

        self.assertIsNone(views._parse_reset_token('not-a-valid-token'))

    def test_login_rate_key(self):
        from types import SimpleNamespace
        from brgy.views import _login_rate_key
        req = SimpleNamespace(META={'REMOTE_ADDR': '192.168.1.10'})
        k1 = _login_rate_key(req, 'alice')
        k2 = _login_rate_key(req, 'alice')
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, _login_rate_key(req, 'bob'))
        other = SimpleNamespace(META={'REMOTE_ADDR': '192.168.1.99'})
        self.assertNotEqual(k1, _login_rate_key(other, 'alice'))
        self.assertTrue(k1)
        self.assertNotIn('alice', k1)


if __name__ == '__main__':
    unittest.main(verbosity=2)