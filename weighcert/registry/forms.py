from django import forms
from django.forms import inlineformset_factory
from .models import Instrument, InstrumentRange, Owner, TestWeight


class OwnerForm(forms.ModelForm):
    class Meta:
        model = Owner
        fields = ["name", "address", "contact_person", "phone", "email", "gstin_or_id"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm focus:ring-2 focus:ring-[#012357]", "required": True}),
            "address": forms.Textarea(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "rows": 2}),
            "contact_person": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "phone": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "email": forms.EmailInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "gstin_or_id": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
        }


class InstrumentForm(forms.ModelForm):
    class Meta:
        model = Instrument
        exclude = ["instrument_id", "created_at", "updated_at"]
        widgets = {
            "owner": forms.Select(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "manufacturer": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "required": True}),
            "model": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "serial_number": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "required": True}),
            "accuracy_class": forms.Select(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "max_capacity_g": forms.NumberInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "step": "any", "required": True}),
            "min_capacity_g": forms.NumberInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "step": "any", "required": True}),
            "e_g": forms.NumberInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "step": "any", "required": True}),
            "d_g": forms.NumberInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "step": "any", "required": True}),
            "unit": forms.Select(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "indication_type": forms.Select(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "load_receptor_type": forms.Select(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "points_of_support": forms.NumberInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "tare_type": forms.Select(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "zero_setting_type": forms.Select(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "place_of_use": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "location_address": forms.Textarea(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "rows": 2}),
            "gravity_zone": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
        }


InstrumentRangeFormSet = inlineformset_factory(
    Instrument,
    InstrumentRange,
    fields=["order", "max_i_g", "e_i_g", "d_i_g"],
    extra=1,
    can_delete=True,
    widgets={
        "order": forms.NumberInput(attrs={"class": "w-16 border rounded px-2 py-1 text-sm"}),
        "max_i_g": forms.NumberInput(attrs={"class": "w-28 border rounded px-2 py-1 text-sm", "step": "any"}),
        "e_i_g": forms.NumberInput(attrs={"class": "w-28 border rounded px-2 py-1 text-sm", "step": "any"}),
        "d_i_g": forms.NumberInput(attrs={"class": "w-28 border rounded px-2 py-1 text-sm", "step": "any"}),
    }
)


class TestWeightForm(forms.ModelForm):
    class Meta:
        model = TestWeight
        fields = [
            "label_id", "nominal_mass_g", "oiml_class", "certificate_number",
            "certified_correction_g", "expanded_uncertainty_g",
            "calibrated_on", "calibration_due_date", "is_active"
        ]
        widgets = {
            "label_id": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "required": True}),
            "nominal_mass_g": forms.NumberInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "step": "any", "required": True}),
            "oiml_class": forms.Select(attrs={"class": "w-full border rounded px-3 py-2 text-sm"}),
            "certificate_number": forms.TextInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "required": True}),
            "certified_correction_g": forms.NumberInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "step": "any"}),
            "expanded_uncertainty_g": forms.NumberInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "step": "any"}),
            "calibrated_on": forms.DateInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "type": "date"}),
            "calibration_due_date": forms.DateInput(attrs={"class": "w-full border rounded px-3 py-2 text-sm", "type": "date", "required": True}),
        }

