from django.urls import path
from . import views

urlpatterns = [
    path("", views.report_archive_view, name="report_archive"),
    path("<int:report_id>/", views.report_preview_view, name="report_preview"),
    path("<int:report_id>/pdf/", views.report_pdf_download_view, name="report_pdf_download"),
]

