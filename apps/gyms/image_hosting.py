"""External image hosting helpers.

New gym uploads are sent to ImgBB and only the returned URL/metadata are stored
in the database. No uploaded owner image is saved under MEDIA_ROOT.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class ImageHostingError(RuntimeError):
    """Raised when a remote image upload cannot be completed safely."""


@dataclass(frozen=True)
class HostedImage:
    id: str
    url: str
    display_url: str
    delete_url: str
    width: int | None
    height: int | None
    size: int | None


def _api_key() -> str:
    value = getattr(settings, "IMGBB_API_KEY", "") or os.getenv("IMGBB_API_KEY", "")
    value = str(value).strip()
    if not value:
        raise ImageHostingError("IMGBB_API_KEY is not configured.")
    return value


def _read_bytes(file_obj: BinaryIO) -> bytes:
    try:
        file_obj.seek(0)
    except Exception:
        pass
    content = file_obj.read()
    try:
        file_obj.seek(0)
    except Exception:
        pass
    if not content:
        raise ImageHostingError("The uploaded image is empty.")
    return content


def upload_image(file_obj: BinaryIO, *, name: str = "") -> HostedImage:
    """Upload one image to ImgBB using API v1.

    ImgBB accepts base64 in the POST body, which lets us avoid writing the file
    to local media storage first.
    """

    raw = _read_bytes(file_obj)
    max_bytes = 32 * 1024 * 1024
    if len(raw) > max_bytes:
        raise ImageHostingError("ImgBB accepts images up to 32 MB.")

    clean_name = Path(name or getattr(file_obj, "name", "image")).stem[:120]
    body_fields = {"image": base64.b64encode(raw).decode("ascii")}
    if clean_name:
        body_fields["name"] = clean_name

    body = urlencode(body_fields).encode("utf-8")
    endpoint = f"https://api.imgbb.com/1/upload?{urlencode({'key': _api_key()})}"
    request = Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "myGym/1.0",
        },
        method="POST",
    )
    timeout = float(getattr(settings, "IMGBB_TIMEOUT_SECONDS", 30))

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise ImageHostingError(f"ImgBB upload failed with HTTP {exc.code}. {detail}".strip()) from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ImageHostingError(f"ImgBB upload failed: {exc}") from exc

    if not payload.get("success") or not isinstance(payload.get("data"), dict):
        raise ImageHostingError("ImgBB returned an unsuccessful upload response.")

    data = payload["data"]
    url = data.get("url") or data.get("display_url")
    if not url:
        raise ImageHostingError("ImgBB response did not include an image URL.")

    def _int_or_none(value):
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return HostedImage(
        id=str(data.get("id") or ""),
        url=str(url),
        display_url=str(data.get("display_url") or url),
        delete_url=str(data.get("delete_url") or ""),
        width=_int_or_none(data.get("width")),
        height=_int_or_none(data.get("height")),
        size=_int_or_none(data.get("size")),
    )
