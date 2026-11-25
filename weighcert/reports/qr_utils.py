import qrcode
import io
import base64


def generate_qr_base64(url: str) -> str:
    """Generate base64 encoded PNG QR code."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#012357", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_val = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_val}"

