"""Generate a downloadable PDF review report for a single video.

Includes video metadata, the suggested outcome, a defect summary, the
checklist, the AI summary/score, a table of timestamped findings, and
thumbnail images of representative flagged frames extracted with OpenCV.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import cv2
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

OUTCOME_COLORS = {
    "pass": colors.HexColor("#2e9e5b"),
    "fail": colors.HexColor("#d6404e"),
    "review": colors.HexColor("#c79121"),
}


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("Tiny", parent=s["Normal"], fontSize=8, textColor=colors.grey))
    s.add(ParagraphStyle("H2b", parent=s["Heading2"], spaceBefore=10, spaceAfter=4))
    return s


def _thumbnails(video_path: str, findings: list[dict], max_thumbs: int = 6) -> list[tuple[str, Image]]:
    """Extract a few flagged frames as reportlab Images (timestamp, image)."""
    if not findings:
        return []
    cap = cv2.VideoCapture(video_path)
    out: list[tuple[str, Image]] = []
    # Spread the selection across the findings list.
    step = max(1, len(findings) // max_thumbs)
    for f in findings[::step][:max_thumbs]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f["frame_index"]))
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = 360 / max(w, 1)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            continue
        img = Image(io.BytesIO(buf.tobytes()))
        img.drawWidth = 55 * mm
        img.drawHeight = 55 * mm * (frame.shape[0] / frame.shape[1])
        label = f"{f['timestamp']}s · {f['defect_type'].replace('_', ' ')} ({f['severity']})"
        out.append((label, img))
    cap.release()
    return out


def build_report_pdf(
    video_id: str,
    video_name: str,
    analysis: dict,
    local_video_path: str | None = None,
    review: dict | None = None,
) -> bytes:
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm)
    story: list = []

    story.append(Paragraph("Video Quality Review Report", s["Title"]))
    story.append(Paragraph(video_name, s["Heading3"]))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Generated {generated}", s["Tiny"]))
    story.append(Spacer(1, 8))

    outcome = (review or {}).get("outcome") or analysis.get("suggested_outcome", "review")
    score = analysis.get("score")
    oc = OUTCOME_COLORS.get(outcome, colors.grey)
    summary_tbl = Table([
        ["Suggested outcome", outcome.upper()],
        ["AI score", f"{score}/100" if score is not None else "—"],
        ["Resolution", analysis.get("resolution", "—")],
        ["Duration", f"{analysis.get('duration_sec', 0)} s"],
        ["Frames (sampled / total)", f"{analysis.get('sampled_frames', 0)} / {analysis.get('total_frames', 0)}"],
        ["AI semantic pass", "yes" if analysis.get("ai", {}).get("ai_used") else "no (local only)"],
    ], colWidths=[55 * mm, 110 * mm])
    summary_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
        ("BACKGROUND", (1, 0), (1, 0), oc),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f3f5")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dde1e6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_tbl)

    # AI / heuristic summary text
    ai_summary = analysis.get("ai", {}).get("summary", "")
    if ai_summary:
        story.append(Paragraph("Analysis summary", s["H2b"]))
        story.append(Paragraph(ai_summary, s["Normal"]))

    # Defect counts
    counts = analysis.get("defect_counts", {})
    story.append(Paragraph("Detected defects", s["H2b"]))
    if counts:
        rows = [["Defect type", "Count"]] + [[k.replace("_", " "), str(v)] for k, v in counts.items()]
        t = Table(rows, colWidths=[110 * mm, 55 * mm])
        t.setStyle(_grid_style())
        story.append(t)
    else:
        story.append(Paragraph("No visual defects detected in sampled frames.", s["Normal"]))

    # Checklist
    checklist = (review or {}).get("checklist") or _checklist_from_suggestion(analysis)
    if checklist:
        story.append(Paragraph("Review checklist", s["H2b"]))
        rows = [["Item", "Status"]] + [[c["label"], str(c["status"]).upper()] for c in checklist]
        t = Table(rows, colWidths=[110 * mm, 55 * mm])
        t.setStyle(_grid_style())
        story.append(t)

    # Findings table (cap to keep PDF readable)
    findings = analysis.get("findings", [])
    if findings:
        story.append(Paragraph("Timestamped findings", s["H2b"]))
        rows = [["Time", "Type", "Severity", "Detail"]]
        for f in findings[:40]:
            rows.append([f"{f['timestamp']}s", f["defect_type"].replace("_", " "),
                         f["severity"], f["message"]])
        t = Table(rows, colWidths=[18 * mm, 32 * mm, 22 * mm, 93 * mm])
        st = _grid_style()
        st.add("FONTSIZE", (0, 0), (-1, -1), 7.5)
        t.setStyle(st)
        story.append(t)
        if len(findings) > 40:
            story.append(Paragraph(f"…and {len(findings) - 40} more.", s["Tiny"]))

    # Comments
    comments = (review or {}).get("comments") or []
    if comments:
        story.append(Paragraph("Reviewer comments", s["H2b"]))
        for c in comments:
            ts = f"[{c['timestamp_sec']}s] " if c.get("timestamp_sec") is not None else ""
            story.append(Paragraph(ts + c.get("text", ""), s["Normal"]))

    # Thumbnails of flagged frames
    if local_video_path and findings:
        thumbs = _thumbnails(local_video_path, findings)
        if thumbs:
            story.append(Paragraph("Flagged frames", s["H2b"]))
            grid_rows, row = [], []
            for label, img in thumbs:
                cell = Table([[img], [Paragraph(label, s["Tiny"])]])
                cell.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
                row.append(cell)
                if len(row) == 3:
                    grid_rows.append(row); row = []
            if row:
                grid_rows.append(row)
            grid = Table(grid_rows, hAlign="LEFT")
            grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 4),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
            story.append(grid)

    doc.build(story)
    return buf.getvalue()


def _grid_style() -> TableStyle:
    return TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b212b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dde1e6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f8fa")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])


def _checklist_from_suggestion(analysis: dict) -> list[dict]:
    labels = {
        "audio_sync": "Audio synchronization",
        "logo_visibility": "Logo visibility",
        "text_readability": "Text readability",
        "dropped_or_frozen_frames": "Dropped or frozen frames",
        "black_or_blank_frames": "Black / blank frames",
        "visual_clarity": "Visual clarity (no blur)",
    }
    sug = analysis.get("suggested_checklist", {})
    return [{"label": labels.get(k, k), "status": v} for k, v in sug.items()]
