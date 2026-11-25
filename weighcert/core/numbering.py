from django.db import transaction
from django.utils import timezone
from .models import LabSettings


def generate_next_report_number() -> str:
    """
    Generate an atomic, sequential report number: PREFIX/YEAR/000001
    Guaranteed unique and non-skipping via DB row lock.
    """
    current_year = timezone.now().year
    with transaction.atomic():
        settings = LabSettings.objects.select_for_update().get(id=1)
        
        # Check year reset policy
        if settings.year_reset_policy == "calendar":
            if settings.counter_year != current_year:
                settings.counter_year = current_year
                settings.report_counter = 0

        settings.report_counter += 1
        counter_val = settings.report_counter
        settings.save()

        prefix = settings.report_number_prefix or "WC"
        year_str = str(settings.counter_year)
        seq_str = f"{counter_val:06d}"
        return f"{prefix}/{year_str}/{seq_str}"

