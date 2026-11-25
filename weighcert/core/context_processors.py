from .models import LabSettings


def lab_settings(request):
    try:
        settings_obj = LabSettings.get_settings()
    except Exception:
        settings_obj = None
    return {"lab_settings": settings_obj}

