"""Google Drive integration: list video files and stream their bytes."""
from __future__ import annotations

import io

from ..config import Settings

VIDEO_MIME_PREFIX = "video/"
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _build_credentials(settings: Settings):
    """Build google credentials from a service-account file or ADC."""
    if settings.google_credentials_file:
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(
            settings.google_credentials_file, scopes=SCOPES
        )
    # Application Default Credentials (e.g. on GCP / `gcloud auth`).
    import google.auth

    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


class DriveService:
    def __init__(self, settings: Settings):
        from googleapiclient.discovery import build

        self.settings = settings
        self.creds = _build_credentials(settings)
        self.service = build("drive", "v3", credentials=self.creds, cache_discovery=False)

    def list_videos(self, folder_id: str | None = None) -> list[dict]:
        folder_id = folder_id or self.settings.google_drive_folder_id
        if not folder_id:
            raise ValueError("No Drive folder provided (paste a folder link or set GOOGLE_DRIVE_FOLDER_ID).")
        query = f"'{folder_id}' in parents and mimeType contains 'video/' and trashed = false"
        results = self.service.files().list(
            q=query,
            fields="files(id, name, mimeType, size, modifiedTime)",
            pageSize=1000,
            orderBy="name",
        ).execute()
        return results.get("files", [])

    def download_to_path(self, file_id: str, dest_path: str) -> str:
        """Download a Drive file to local disk (used for analysis)."""
        from googleapiclient.http import MediaIoBaseDownload

        request = self.service.files().get_media(fileId=file_id)
        with open(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return dest_path

    def stream(self, file_id: str):
        """Yield file bytes in chunks for HTTP streaming/preview."""
        from googleapiclient.http import MediaIoBaseDownload

        request = self.service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            buffer.seek(0)
            chunk = buffer.read()
            if chunk:
                yield chunk
            buffer.seek(0)
            buffer.truncate(0)
