from django.urls import path

from ..views import admin as views

urlpatterns = [
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
