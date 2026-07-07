from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from dashboard.views import PrivacyPolicyAPIView, TermsAndConditionsAPIView
from .views import serve_obj_file
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('authentication.urls')),
    path('api/contact/', include('contact_support.urls')),
    path('api/scans/', include('scans.urls')),
    path('api/dashboard/', include('dashboard.urls')),
    path('api/privacy-policy/', PrivacyPolicyAPIView.as_view(), name='privacy-policy'),
    path('api/terms-and-conditions/', TermsAndConditionsAPIView.as_view(), name='terms-and-conditions'),
    path('api/notifications/', include('notifications.urls')),
    re_path(r'^media/scans/outputs/(?P<filename>[^/]+\.(obj|glb))$', serve_obj_file, name='serve-obj-file'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)