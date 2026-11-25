import os
import io
from django.template.loader import render_to_string
from django.conf import settings
from .qr_utils import generate_qr_base64


def render_report_pdf(report, request=None) -> bytes:
    """
    Render A4 PDF report matching Spec Section 10.
    Tries WeasyPrint first; gracefully falls back to xhtml2pdf if GTK3 libraries are unavailable.
    """
    verify_url = f"http://127.0.0.1:8000/verify/{report.verification_token}/"
    if request:
        verify_url = request.build_absolute_uri(f"/verify/{report.verification_token}/")

    qr_b64 = generate_qr_base64(verify_url)
    session = report.session
    instrument = session.instrument

    context = {
        "report": report,
        "session": session,
        "instrument": instrument,
        "owner": instrument.owner,
        "qr_code_b64": qr_b64,
        "verify_url": verify_url,
        "accuracy_up": session.accuracy_readings.filter(phase="up"),
        "accuracy_down": session.accuracy_readings.filter(phase="down"),
        "weights": session.session_weights.select_related("weight").all(),
        "zero_check": getattr(session, "zero_check", None),
        "repeatability": getattr(session, "repeatability_test", None),
        "eccentricity": getattr(session, "eccentricity_test", None),
        "is_pdf": True,
    }

    html_string = render_to_string("reports/report_print.html", context)

    # 1. Try WeasyPrint
    try:
        from weasyprint import HTML
        base_url = str(settings.BASE_DIR)
        return HTML(string=html_string, base_url=base_url).write_pdf()
    except Exception as e:
        # 2. Fallback to xhtml2pdf (pisa)
        from xhtml2pdf import pisa
        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(html_string, dest=pdf_buffer)
        if not pisa_status.err:
            return pdf_buffer.getvalue()
        raise RuntimeError(f"PDF rendering error: {e}")


def generate_and_save_pdf(report, request=None) -> str:
    """Generate PDF and save to media/generated_reports/."""
    pdf_bytes = render_report_pdf(report, request)
    clean_num = report.report_number.replace("/", "_")
    clean_sn = report.session.instrument.serial_number.replace("/", "_")
    filename = f"NAWI_{clean_num}_{clean_sn}_rev{report.revision}.pdf"

    reports_dir = os.path.join(settings.MEDIA_ROOT, "generated_reports")
    os.makedirs(reports_dir, exist_ok=True)
    full_path = os.path.join(reports_dir, filename)

    with open(full_path, "wb") as f:
        f.write(pdf_bytes)

    rel_path = f"generated_reports/{filename}"
    report.pdf_file = rel_path
    report.save(update_fields=["pdf_file"])
    return rel_path
