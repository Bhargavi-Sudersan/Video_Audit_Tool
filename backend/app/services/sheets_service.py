"""Google Sheets integration: store and read review records centrally."""
from __future__ import annotations

import json

from ..config import Settings
from ..models.schemas import ReviewRecord
from .drive_service import _build_credentials

HEADER = [
    "video_id", "video_name", "reviewer", "outcome", "status",
    "score", "checklist_json", "comments_json", "ai_summary", "updated_at",
]


class SheetsService:
    def __init__(self, settings: Settings):
        from googleapiclient.discovery import build

        self.settings = settings
        self.spreadsheet_id = settings.google_sheets_spreadsheet_id
        self.tab = settings.google_sheets_reviews_tab
        self.creds = _build_credentials(settings)
        self.service = build("sheets", "v4", credentials=self.creds, cache_discovery=False)
        self._ensure_header()

    def _range(self, a1: str) -> str:
        return f"{self.tab}!{a1}"

    def _ensure_header(self) -> None:
        values = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=self._range("A1:J1")
        ).execute().get("values", [])
        if not values:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=self._range("A1"),
                valueInputOption="RAW",
                body={"values": [HEADER]},
            ).execute()

    def _row(self, r: ReviewRecord) -> list:
        return [
            r.video_id, r.video_name, r.reviewer, r.outcome.value, r.status.value,
            r.score if r.score is not None else "",
            json.dumps([c.model_dump() for c in r.checklist]),
            json.dumps([c.model_dump() for c in r.comments]),
            r.ai_summary, r.updated_at,
        ]

    def upsert(self, record: ReviewRecord) -> None:
        rows = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=self._range("A2:J")
        ).execute().get("values", [])
        target_row = None
        for i, row in enumerate(rows):
            if row and row[0] == record.video_id:
                target_row = i + 2  # 1-based + header
                break
        body = {"values": [self._row(record)]}
        if target_row:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=self._range(f"A{target_row}:J{target_row}"),
                valueInputOption="RAW", body=body,
            ).execute()
        else:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=self._range("A2:J"),
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS", body=body,
            ).execute()

    def list_records(self) -> list[dict]:
        rows = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=self._range("A2:J")
        ).execute().get("values", [])
        records = []
        for row in rows:
            row = row + [""] * (len(HEADER) - len(row))
            records.append({
                "video_id": row[0], "video_name": row[1], "reviewer": row[2],
                "outcome": row[3] or "review", "status": row[4] or "completed",
                "score": float(row[5]) if row[5] not in ("", None) else None,
                "checklist": json.loads(row[6]) if row[6] else [],
                "comments": json.loads(row[7]) if row[7] else [],
                "ai_summary": row[8], "updated_at": row[9],
            })
        return records
