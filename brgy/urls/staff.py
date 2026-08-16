from django.urls import path

from ..views import staff as views

urlpatterns = [
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
]
