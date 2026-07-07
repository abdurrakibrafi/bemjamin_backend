from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DashboardStatsAPIView,
    UserOverviewChartAPIView,
    ScannerOverviewChartAPIView,
    UserManagementViewSet,
    ScanManagementViewSet,
    ContactMessageViewSet,
    PushNotificationHistoryViewSet, 
    AdminNotificationViewSet,
    SiteContentViewSet,
    AdminProfileView,
    AdminChangePasswordView,
    SendPushNotificationAPIView,    
)

router = DefaultRouter()
router.register(r'users', UserManagementViewSet, basename='dashboard-user')
router.register(r'scans', ScanManagementViewSet, basename='dashboard-scan')
router.register(r'contacts', ContactMessageViewSet, basename='dashboard-contact')
router.register(r'admin-notifications', AdminNotificationViewSet, basename='admin-notification')
router.register(r'content', SiteContentViewSet, basename='site-content')
router.register(r'push-notifications-history', PushNotificationHistoryViewSet, basename='push-notification-history')


urlpatterns = [
    path('stats/', DashboardStatsAPIView.as_view(), name='dashboard-stats'),
    path('charts/user-overview/', UserOverviewChartAPIView.as_view(), name='chart-user-overview'),
    path('charts/scanner-overview/', ScannerOverviewChartAPIView.as_view(), name='chart-scanner-overview'),
    path('settings/profile/', AdminProfileView.as_view(), name='admin-profile'),
    path('settings/change-password/', AdminChangePasswordView.as_view(), name='admin-change-password'),
    path('push-notifications/send/', SendPushNotificationAPIView.as_view(), name='send-push-notification'),
    path('', include(router.urls)),
]