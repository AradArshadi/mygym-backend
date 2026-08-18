import base64
import io


def build_qr_data_uri(payload: str) -> str:
    """Return a PNG data URI for a QR payload.

    qrcode is listed in requirements. If the package is unavailable during a partial install,
    return an empty string so templates can fall back to showing the URL.
    """
    try:
        import qrcode
    except Exception:
        return ''

    image = qrcode.make(payload)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'data:image/png;base64,{encoded}'
