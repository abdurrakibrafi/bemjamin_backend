# scans/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ScanViewSet

# DefaultRouter automatically creates the standard URLs for a ViewSet
# (e.g., /scans/, /scans/{id}/)
router = DefaultRouter()
router.register(r'', ScanViewSet, basename='scan')

urlpatterns = [
    path('', include(router.urls)),
]