from django.urls import path
from . import views

urlpatterns = [
    # Landing Page
    path('', views.home_page, name='home'),

    # Auth
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard redirect
    path('dashboard/', views.dashboard_redirect, name='dashboard'),

    # Resident
    path('resident/', views.resident_dashboard, name='resident_dashboard'),
    path('resident/profile/', views.resident_profile, name='profile'), 
    
    # Document Requests
    path('resident/request/', views.request_document, name='request_document'),
    
    # NEW: Submit bulk request from the modal
    path('resident/request/submit-bulk/', views.submit_bulk_request, name='submit_bulk_request'),
    
    path('resident/history/', views.request_history, name='request_history'),
    path('resident/notifications/', views.notifications_view, name='notifications'),
    path('resident/notifications/read/<uuid:pk>/', views.mark_notification_read, name='mark_notification_read'),
    path('resident/notifications/read-all/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('resident/history/cancel/<uuid:pk>/', views.cancel_request, name='cancel_request'),
    path('resident/history/track/<uuid:pk>/', views.track_request, name='track_request'),

    # Staff
    path('staff/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/verify-residents/', views.verify_residents, name='verify_residents'),
    path('staff/verify-residents/<uuid:pk>/approve/', views.approve_resident, name='approve_resident'),
    path('staff/verify-residents/<uuid:pk>/reject/', views.reject_resident, name='reject_resident'),
    path('staff/requests/', views.manage_requests, name='manage_requests'),
    path('staff/requests/<uuid:pk>/', views.update_request_status, name='update_request_status'),
    path('staff/requests/<uuid:pk>/reject/', views.reject_request, name='reject_request'),
    path('staff/reports/', views.staff_reports, name='staff_reports'),
    path('staff/document-types/', views.staff_manage_document_types, name='staff_manage_document_types'),
    path('staff/document-types/<uuid:pk>/edit/', views.staff_edit_document_type, name='staff_edit_document_type'),
    path('staff/document-types/<uuid:pk>/delete/', views.staff_delete_document_type, name='staff_delete_document_type'),
    path('staff/requests/print/<uuid:req_pk>/<uuid:item_pk>/', views.print_document, name='print_document'),

    # Admin
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/staff/', views.manage_staff, name='manage_staff'),
    path('admin/staff/<uuid:pk>/edit/', views.edit_staff, name='edit_staff'),
    path('admin/staff/<uuid:pk>/toggle/', views.toggle_staff_active, name='toggle_staff_active'),
    path('admin/barangays/', views.manage_barangays, name='manage_barangays'),
    path('admin/barangays/<uuid:pk>/edit/', views.edit_barangay, name='edit_barangay'),
    path('admin/barangays/<uuid:pk>/logo/', views.change_barangay_logo, name='change_barangay_logo'),
    path('admin/document-types/', views.manage_document_types, name='manage_document_types'),
    path('admin/document-types/<uuid:pk>/edit/', views.edit_document_type, name='edit_document_type'),
    path('admin/document-types/<uuid:pk>/delete/', views.delete_document_type, name='delete_document_type'),
    path('admin/activity-logs/', views.activity_logs, name='activity_logs'),
]