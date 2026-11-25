from decimal import Decimal
from django import template

register = template.Library()

@register.filter(name="format_mass")
def format_mass(val, unit="g"):
    """
    Format mass in grams to readable string.
    Usage: {{ val_in_grams|format_mass }} or {{ val_in_grams|format_mass:"kg" }}
    """
    if val is None or val == "":
        return ""
    try:
        d = Decimal(str(val))
    except Exception:
        return str(val)

    if unit == "kg" or (unit == "g" and d >= Decimal("1000")):
        kg = d / Decimal("1000")
        return f"{kg.normalize():f} kg"
    elif unit == "mg":
        mg = d * Decimal("1000")
        return f"{mg.normalize():f} mg"
    elif unit == "t":
        t = d / Decimal("1000000")
        return f"{t.normalize():f} t"
    return f"{d.normalize():f} g"

