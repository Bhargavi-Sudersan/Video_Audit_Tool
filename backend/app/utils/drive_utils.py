"""Parse Google Drive folder / file IDs out of the many link formats users
paste, so the UI can accept a raw link instead of a bare ID.

Supported inputs:
  https://drive.google.com/drive/folders/<ID>
  https://drive.google.com/drive/u/0/folders/<ID>?usp=sharing
  https://drive.google.com/drive/u/2/folders/<ID>
  https://drive.google.com/file/d/<ID>/view
  https://drive.google.com/open?id=<ID>
  <ID>                      (already a bare id)
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_FOLDER_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")
_FILE_RE = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
_BARE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,}$")


def parse_drive_id(value: str) -> str | None:
    """Return the Drive folder or file id from a link or bare id, else None."""
    if not value:
        return None
    value = value.strip()

    if _BARE_ID_RE.match(value) and "/" not in value:
        return value

    m = _FOLDER_RE.search(value) or _FILE_RE.search(value)
    if m:
        return m.group(1)

    # ...?id=<ID> style
    try:
        qs = parse_qs(urlparse(value).query)
        if "id" in qs and qs["id"]:
            return qs["id"][0]
    except ValueError:
        pass
    return None
