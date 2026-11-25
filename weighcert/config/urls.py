"""WeighCert URL configuration."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("core.urls")),
    path("instruments/", include("registry.urls")),
    path("tests/", include("inspections.urls")),
    path("reports/", include("reports.urls")),
    path("verify/", include("reports.verify_urls")),
    path("weights/", include("registry.weight_urls")),
    path("settings/", include("core.settings_urls")),
    path("sysadmin/", include("accounts.sysadmin_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

