import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, Http404
from django.contrib import messages
from django.db.models import Q
from accounts.decorators import staff_required
from .models import Report
from .pdf import render_report_pdf, generate_and_save_pdf
from .snapshot import verify_report_integrity
from .qr_utils import generate_qr_base64


@staff_required
def report_preview_view(request, report_id):
    """Page 7: Report Preview (A4 paper on canvas)"""
    report = get_object_or_404(
        Report.objects.select_related(
            "session", "session__instrument", "session__instrument__owner", "approved_by", "session__inspector"
        ),
        id=report_id
    )
    session = report.session
    instrument = session.instrument

    verify_url = request.build_absolute_uri(f"/verify/{report.verification_token}/")
    qr_b64 = generate_qr_base64(verify_url)

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
        "is_pdf": False,
    }
    return render(request, "reports/report_preview.html", context)


@staff_required
def report_pdf_download_view(request, report_id):
    """Download WeasyPrint-generated PDF report."""
    report = get_object_or_404(Report, id=report_id)
    pdf_bytes = render_report_pdf(report, request)

    clean_num = report.report_number.replace("/", "_")
    clean_sn = report.session.instrument.serial_number.replace("/", "_")
    filename = f"NAWI_{clean_num}_{clean_sn}_rev{report.revision}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@staff_required
def report_archive_view(request):
    """Page 8: Reports Archive with multi-criteria filtering."""
    q_search = request.GET.get("q", "").strip()
    result_filter = request.GET.get("result", "").strip()
    status_filter = request.GET.get("status", "").strip()
    type_filter = request.GET.get("type", "").strip()

    qs = Report.objects.select_related(
        "session", "session__instrument", "session__instrument__owner", "approved_by"
    ).all()

    if q_search:
        qs = qs.filter(
            Q(report_number__icontains=q_search) |
            Q(session__instrument__serial_number__icontains=q_search) |
            Q(session__instrument__owner__name__icontains=q_search) |
            Q(session__instrument__manufacturer__icontains=q_search)
        )
    if result_filter:
        qs = qs.filter(session__overall_result=result_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if type_filter:
        qs = qs.filter(session__inspection_type=type_filter)

    # Export to CSV if requested
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="WeighCert_Reports_Archive.csv"'
        writer = csv.writer(response)
        writer.writerow(["Report Number", "Revision", "Date Issued", "Owner", "Instrument Serial", "Class", "Inspection Type", "Result", "Status"])
        for rep in qs:
            writer.writerow([
                rep.report_number,
                rep.revision,
                rep.issued_at.strftime("%Y-%m-%d %H:%M"),
                rep.session.instrument.owner.name,
                rep.session.instrument.serial_number,
                rep.session.instrument.accuracy_class,
                rep.session.get_inspection_type_display(),
                rep.session.get_overall_result_display(),
                rep.get_status_display(),
            ])
        return response

    context = {
        "reports": qs,
        "q_search": q_search,
        "result_filter": result_filter,
        "status_filter": status_filter,
        "type_filter": type_filter,
    }
    return render(request, "reports/archive.html", context)


def public_verify_view(request, token=None):
    """
    Page 9: Public Verification (no login required).
    Recomputed snapshot hash check proves integrity.
    Spec Section 9.3 (Page 9) & 11.2
    """
    report = None
    integrity_status = None
    integrity_message = ""
    queried = False

    if token:
        queried = True
        report = Report.objects.select_related(
            "session", "session__instrument"
        ).filter(verification_token=token).first()
    elif request.method == "POST":
        queried = True
        rep_num = request.POST.get("report_number", "").strip()
        v_code = request.POST.get("token", "").strip()
        if v_code:
            report = Report.objects.filter(verification_token=v_code).first()
        elif rep_num:
            report = Report.objects.filter(report_number=rep_num).order_by("-revision").first()

    if report:
        is_intact, integrity_message = verify_report_integrity(report)
        integrity_status = "valid" if is_intact else "altered"
        if report.status == Report.STATUS_SUPERSEDED and is_intact:
            integrity_status = "superseded"

    context = {
        "report": report,
        "token": token,
        "queried": queried,
        "integrity_status": integrity_status,
        "integrity_message": integrity_message,
    }
    return render(request, "reports/verify.html", context)

