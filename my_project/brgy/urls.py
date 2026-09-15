from django.urls import path
from . import views

urlpatterns = [
    # Landing Page
    path('', views.home_page, name='home'),
    path('services/', views.services_page, name='services'),
    path('about/', views.about_page, name='about'),

    # Auth
    path('login/', views.login_view, name='login'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', views.password_reset, name='password_reset'),
    path('password-reset/<str:token>/', views.password_reset_confirm, name='password_reset_confirm'),

    # Dashboard redirect
    path('dashboard/', views.dashboard_redirect, name='dashboard'),
    path('verify/', views.verify_document_view, name='verify_document'),

    # Resident
    path('resident/', views.resident_dashboard, name='resident_dashboard'),
    path('resident/profile/', views.resident_profile, name='profile'),
    path('resident/password/', views.resident_password_change, name='resident_password_change'), 
    
    # Document Requests
    path('resident/request/', views.request_document, name='request_document'),
    path('resident/request/preview/<uuid:pk>/', views.document_preview, name='document_preview'),
    
    # NEW: Submit bulk request from the modal
    path('resident/request/submit-bulk/', views.submit_bulk_request, name='submit_bulk_request'),
    
    path('resident/history/', views.request_history, name='request_history'),
    path('resident/notifications/', views.notifications_view, name='notifications'),
    path('resident/notifications/read/<uuid:pk>/', views.mark_notification_read, name='mark_notification_read'),
    path('resident/notifications/read-all/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/count/', views.unread_notification_count, name='unread_notification_count'),
    path('resident/history/cancel/<uuid:pk>/', views.cancel_request, name='cancel_request'),
    path('resident/history/track/<uuid:pk>/', views.track_request, name='track_request'),
    path('resident/history/track/<uuid:pk>/<uuid:item_pk>/', views.track_request, name='track_request_item'),

    # Staff
    path('staff/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/profile/', views.staff_profile, name='staff_profile'),
    path('staff/notifications/', views.staff_notifications, name='staff_notifications'),
    path('staff/verify-residents/', views.verify_residents, name='verify_residents'),
    path('staff/verify-residents/<uuid:pk>/approve/', views.approve_resident, name='approve_resident'),
    path('staff/verify-residents/<uuid:pk>/reject/', views.reject_resident, name='reject_resident'),
    path('staff/verify-residents/<uuid:pk>/toggle-active/', views.toggle_resident_active, name='toggle_resident_active'),
    path('staff/requests/', views.manage_requests, name='manage_requests'),
    path('staff/requests/<uuid:pk>/', views.update_request_status, name='update_request_status'),
    path('staff/requests/<uuid:pk>/ready/', views.mark_ready_for_pickup, name='mark_ready_for_pickup'),
    path('staff/requests/<uuid:pk>/paid/', views.mark_paid, name='mark_paid'),
    path('staff/requests/<uuid:pk>/reject/', views.reject_request, name='reject_request'),
    path('staff/reports/', views.staff_reports, name='staff_reports'),
    path('staff/reports/export/', views.staff_reports_export, name='staff_reports_export'),
    path('staff/announcements/', views.manage_announcements, name='manage_announcements'),
    path('staff/announcements/<uuid:pk>/toggle/', views.toggle_announcement, name='toggle_announcement'),
    path('staff/announcements/<uuid:pk>/delete/', views.delete_announcement, name='delete_announcement'),
    path('staff/document-types/', views.staff_manage_document_types, name='staff_manage_document_types'),
    path('staff/document-types/<uuid:pk>/edit/', views.staff_edit_document_type, name='staff_edit_document_type'),
    path('staff/document-types/<uuid:pk>/configure/', views.staff_edit_global_type, name='staff_edit_global_type'),
    path('staff/document-types/<uuid:pk>/delete/', views.staff_delete_document_type, name='staff_delete_document_type'),
    path('staff/requests/print/<uuid:req_pk>/<uuid:item_pk>/', views.print_document, name='print_document'),
    path('staff/requests/print/<uuid:req_pk>/<uuid:item_pk>/mark-printed/', views.mark_printed, name='mark_printed'),
    path('staff/requests/<uuid:req_pk>/files/<uuid:item_pk>/<int:index>/', views.requirement_file, name='requirement_file'),

    # Admin
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/profile/', views.admin_profile, name='admin_profile'),
    path('admin/staff/', views.manage_staff, name='manage_staff'),
    path('admin/staff/<uuid:pk>/edit/', views.edit_staff, name='edit_staff'),
    path('admin/staff/<uuid:pk>/toggle/', views.toggle_staff_active, name='toggle_staff_active'),
    path('admin/staff/<uuid:pk>/reset-password/', views.reset_staff_password, name='reset_staff_password'),
    path('admin/barangays/', views.manage_barangays, name='manage_barangays'),
    path('admin/barangays/<uuid:pk>/edit/', views.edit_barangay, name='edit_barangay'),
    path('admin/barangays/<uuid:pk>/logo/', views.change_barangay_logo, name='change_barangay_logo'),
    path('admin/document-types/', views.manage_document_types, name='manage_document_types'),
    path('admin/document-types/<uuid:pk>/edit/', views.edit_document_type, name='edit_document_type'),
    path('admin/document-types/<uuid:pk>/delete/', views.delete_document_type, name='delete_document_type'),
    path('admin/activity-logs/', views.activity_logs, name='activity_logs'),
    path('admin/activity-logs/export/', views.activity_logs_export, name='activity_logs_export'),
    path('admin/reports/', views.admin_reports, name='admin_reports'),
    path('admin/reports/export/', views.admin_reports_export, name='admin_reports_export'),
    path('admin/notifications/', views.notifications_view, name='admin_notifications'),
]