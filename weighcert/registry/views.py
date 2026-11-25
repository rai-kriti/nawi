from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from decimal import Decimal
from accounts.decorators import inspector_required, staff_required, admin_required
from core.audit import log_audit
from rules.engine import validate_instrument, RangeSpec
from .models import Instrument, InstrumentRange, Owner, TestWeight
from .forms import InstrumentForm, InstrumentRangeFormSet, OwnerForm, TestWeightForm


@staff_required
def instrument_list_view(request):
    """Page 3: Instruments List"""
    query = request.GET.get("q", "").strip()
    cls_filter = request.GET.get("class", "").strip()
    status_filter = request.GET.get("status", "").strip()

    qs = Instrument.objects.select_related("owner").all()

    if query:
        qs = qs.filter(
            Q(serial_number__icontains=query) |
            Q(manufacturer__icontains=query) |
            Q(model__icontains=query) |
            Q(owner__name__icontains=query) |
            Q(instrument_id__icontains=query)
        )
    if cls_filter:
        qs = qs.filter(accuracy_class=cls_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    context = {
        "instruments": qs,
        "query": query,
        "cls_filter": cls_filter,
        "status_filter": status_filter,
    }
    return render(request, "registry/instrument_list.html", context)


@inspector_required
def instrument_create_view(request):
    """Page 4: Create Instrument"""
    form = InstrumentForm(request.POST or None)
    formset = InstrumentRangeFormSet(request.POST or None)
    owner_form = OwnerForm()

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            inst = form.save()
            formset.instance = inst
            formset.save()
            log_audit(request.user, "create", "Instrument", str(inst.id), after={"serial_number": inst.serial_number})
            messages.success(request, f"Instrument {inst.instrument_id} registered successfully.")
            return redirect("instrument_detail", instrument_id=inst.instrument_id)
        else:
            messages.error(request, "Please correct the highlighted errors.")

    owners = Owner.objects.all()
    context = {
        "form": form,
        "formset": formset,
        "owner_form": owner_form,
        "owners": owners,
        "is_create": True,
    }
    return render(request, "registry/instrument_form.html", context)


@staff_required
def instrument_edit_view(request, instrument_id):
    """Page 4: Edit Instrument (Inspector only edit; Officer/Admin view)"""
    inst = get_object_or_404(Instrument, instrument_id=instrument_id)
    if not request.user.profile.is_inspector():
        return redirect("instrument_detail", instrument_id=inst.instrument_id)

    form = InstrumentForm(request.POST or None, instance=inst)
    formset = InstrumentRangeFormSet(request.POST or None, instance=inst)
    owner_form = OwnerForm()

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            log_audit(request.user, "update", "Instrument", str(inst.id), after={"serial_number": inst.serial_number})
            messages.success(request, f"Instrument {inst.instrument_id} updated successfully.")
            return redirect("instrument_detail", instrument_id=inst.instrument_id)

    context = {
        "form": form,
        "formset": formset,
        "owner_form": owner_form,
        "instrument": inst,
        "is_create": False,
    }
    return render(request, "registry/instrument_form.html", context)


@staff_required
def instrument_detail_view(request, instrument_id):
    """Page 4: Instrument Detail & Test History"""
    inst = get_object_or_404(Instrument.objects.select_related("owner"), instrument_id=instrument_id)
    history = inst.test_sessions.select_related("inspector").order_by("-test_date")

    # Run classification validation
    ranges = [
        RangeSpec(order=r.order, max_g=r.max_i_g, e_g=r.e_i_g, d_g=r.d_i_g)
        for r in inst.ranges.all()
    ]
    findings = validate_instrument(
        cls=inst.accuracy_class,
        max_g=inst.max_capacity_g,
        min_g=inst.min_capacity_g,
        e_g=inst.e_g,
        d_g=inst.d_g,
        ranges=ranges,
        is_grading=inst.is_grading,
    )

    context = {
        "instrument": inst,
        "history": history,
        "findings": findings,
    }
    return render(request, "registry/instrument_detail.html", context)


@staff_required
def instrument_validate_api(request):
    """Live validation endpoint for HTMX form."""
    try:
        cls_val = request.GET.get("accuracy_class", "III")
        max_g = Decimal(str(request.GET.get("max_capacity_g", "0") or "0"))
        min_g = Decimal(str(request.GET.get("min_capacity_g", "0") or "0"))
        e_g = Decimal(str(request.GET.get("e_g", "1") or "1"))
        d_g = Decimal(str(request.GET.get("d_g", "1") or "1"))
        is_grading = request.GET.get("is_grading") == "true"

        findings = validate_instrument(
            cls=cls_val, max_g=max_g, min_g=min_g, e_g=e_g, d_g=d_g, is_grading=is_grading
        )
        data = [
            {"code": f.code, "severity": f.severity, "message": f.message, "clause": f.clause}
            for f in findings
        ]
        n_val = (max_g / e_g) if e_g > 0 else 0
        return JsonResponse({"n": str(n_val), "findings": data})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@inspector_required
def owner_create_inline(request):
    """Inline modal / HTMX creation of Owner."""
    form = OwnerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        owner = form.save()
        log_audit(request.user, "create", "Owner", str(owner.id), after={"name": owner.name})
        return JsonResponse({"id": owner.id, "name": owner.name})
    return JsonResponse({"errors": form.errors}, status=400)


# Standard Weights Views (Page 10)
@staff_required
def weight_list_view(request):
    """Page 10: Standard Weights Inventory"""
    weights = TestWeight.objects.all().order_by("nominal_mass_g")
    form = TestWeightForm()
    context = {
        "weights": weights,
        "form": form,
    }
    return render(request, "registry/weight_list.html", context)


@admin_required
def weight_create_view(request):
    form = TestWeightForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        weight = form.save()
        log_audit(request.user, "create", "TestWeight", str(weight.id), after={"label_id": weight.label_id})
        messages.success(request, f"Standard weight {weight.label_id} added.")
    else:
        messages.error(request, "Error adding standard weight.")
    return redirect("weight_list")


@admin_required
def weight_toggle_view(request, weight_id):
    weight = get_object_or_404(TestWeight, id=weight_id)
    weight.is_active = not weight.is_active
    weight.save()
    status_str = "activated" if weight.is_active else "deactivated"
    log_audit(request.user, "update", "TestWeight", str(weight.id), after={"is_active": weight.is_active})
    messages.success(request, f"Weight {weight.label_id} {status_str}.")
    return redirect("weight_list")

