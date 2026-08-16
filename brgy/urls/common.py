from django.urls import path

from ..views import common as views

urlpatterns = [
    # Landing Page
    path('', views.home_page, name='home'),

    # Auth
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard redirect
    path('dashboard/', views.dashboard_redirect, name='dashboard'),

    # Notifications (role-agnostic actions)
    path('resident/notifications/read/<uuid:pk>/', views.mark_notification_read, name='mark_notification_read'),
    path('resident/notifications/read-all/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
]
