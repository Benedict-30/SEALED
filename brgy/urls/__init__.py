from django.urls import include, path

urlpatterns = [
    path('', include('brgy.urls.common')),
    path('', include('brgy.urls.resident')),
    path('', include('brgy.urls.staff')),
    path('', include('brgy.urls.admin')),
]
