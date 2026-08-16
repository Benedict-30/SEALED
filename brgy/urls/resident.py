from django.urls import path

from ..views import resident as views

urlpatterns = [
    path('resident/', views.resident_dashboard, name='resident_dashboard'),
    path('resident/profile/', views.resident_profile, name='profile'),

    # Document Requests
    path('resident/request/', views.request_document, name='request_document'),
    path('resident/request/submit-bulk/', views.submit_bulk_request, name='submit_bulk_request'),

    path('resident/history/', views.request_history, name='request_history'),
    path('resident/notifications/', views.notifications_view, name='notifications'),
    path('resident/history/cancel/<uuid:pk>/', views.cancel_request, name='cancel_request'),
    path('resident/history/track/<uuid:pk>/', views.track_request, name='track_request'),
]
