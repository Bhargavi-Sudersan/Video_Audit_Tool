# Video Audit &amp; Quality Review

An AI-assisted platform for reviewing educational videos, advertisements,
marketing creatives, and media assets. It combines a **manual review
workflow** (frame-by-frame navigation, a structured checklist, timestamped
comments) with **automated defect detection** (blurry / black / frozen /
unreadable-text frames) and centralised review storage in the cloud.

It runs **out of the box in demo mode** with no credentials, and switches to
**Google Drive + Google Sheets** for real cloud workflows by changing one
environment variable.

---

## Contents

- [Architecture](#architecture)
- [Quick start (demo mode)](#quick-start-demo-mode)
- [Running with Docker](#running-with-docker)
- [Connecting Google Drive &amp; Sheets](#connecting-google-drive--sheets)
- [Enabling AI analysis](#enabling-ai-analysis)
- [How the analysis works](#how-the-analysis-works)
- [API reference](#api-reference)
- [Deploying to your git](#deploying-to-your-git)
- [Extending the platform](#extending-the-platform)
- [Project layout](#project-layout)

---

## Architecture

```
                 ┌────────────────────────┐
  Browser ─────► │  React + Vite frontend │  video preview · frame nav ·
                 │  (QA workstation UI)   │  checklist · AI panel · dashboard
                 └───────────┬────────────┘
                             │ /api  (REST + video streaming)
                 ┌───────────▼────────────┐
                 │   FastAPI backend       │
                 │  ┌───────────────────┐  │
                 │  │ frame_sampler     │  │  intelligent sampling
                 │  │ video_analysis    │  │  OpenCV defect heuristics
                 │  │ ai_service        │  │  Claude vision (optional)
                 │  │ storage (Repo)    │  │  pluggable backends
                 │  └───────────────────┘  │
                 └─────┬──────────────┬─────┘
            demo mode  │              │  google mode
        ┌──────────────▼──┐      ┌────▼────────────────────┐
        │ local videos +  │      │ Google Drive (videos) + │
        │ reviews.json    │      │ Google Sheets (reviews) │
        └─────────────────┘      └─────────────────────────┘
```

The storage layer is an abstract `Repository` interface, so adding S3 +
DynamoDB or Azure Blob + Cosmos later is a single new class.

---

## Reviewing videos

You can review a **single video** or a **whole folder** in one run, and the
review depth (local-only vs. AI) is chosen per run via the toggle.

**Single video** — open it from the Library, press **Run analysis**, adjust
the checklist, add comments, **Submit**. **Download PDF** produces a report
for that video.

**Whole folder / multiple** — in the Library, optionally tick specific
videos, then **Review all** (or **Review selected**). This starts a batch
job that analyses each video, derives a pass/review/fail outcome, and saves
a review record centrally. A progress bar shows live status; when done, each
row links to its **PDF report**. Batch results also flow into the Dashboard.

In **google mode**, paste a Google Drive **folder link** in the Library's
Source bar to load that folder's videos (the folder must be shared with the
service-account email). In **demo mode**, local sample videos load
automatically and the link box is hidden.

### Reports

- **Per-video PDF** — `GET /api/reports/{id}.pdf?use_ai=true|false`. Includes
  the outcome, defect summary, checklist, AI summary/score, a timestamped
  findings table, and thumbnail images of flagged frames.
- **CSV of all reviews** — `GET /api/reviews/export.csv` (the **Export CSV**
  button in the top bar).

---

## Quick start (demo mode)

Requirements: Python 3.12+, Node 20+.

**1. Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # defaults to STORAGE_BACKEND=demo

# generate two sample clips (one clean, one with injected defects)
python -m scripts.make_sample_videos

uvicorn app.main:app --reload --port 8000
```

**2. Frontend** (in a second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Go to **Library**, click **Review** on a clip,
press **Run analysis**, adjust the checklist, add comments, and **Submit
evaluation**. The **Dashboard** shows completion and pass/fail metrics;
**Export CSV** downloads all review summaries.

No API keys are needed — AI analysis falls back to deterministic heuristics
and reviews are stored in `backend/data/reviews.json`.

---

## Running with Docker

```bash
cd backend && cp .env.example .env && cd ..
docker compose up --build
```

Frontend is served at <http://localhost:8080> (nginx proxies `/api` to the
backend). To seed demo videos into the mounted volume:

```bash
docker compose exec backend python -m scripts.make_sample_videos
```

---

## Connecting Google Drive &amp; Sheets

1. In Google Cloud, create a project and enable the **Drive API** and
   **Sheets API**.
2. Create a **service account** and download its JSON key. Put it in
   `secrets/` (git-ignored), e.g. `secrets/sa.json`.
3. Create a Drive folder for the videos and a Google Sheet for review data.
   **Share both with the service-account email** (Viewer for the folder,
   Editor for the sheet).
4. Set these in `backend/.env`:

```ini
STORAGE_BACKEND=google
GOOGLE_CREDENTIALS_FILE=./secrets/sa.json     # or /app/secrets/sa.json in Docker
GOOGLE_DRIVE_FOLDER_ID=<folder id from the Drive URL>
GOOGLE_SHEETS_SPREADSHEET_ID=<id from the Sheet URL>
GOOGLE_SHEETS_REVIEWS_TAB=Reviews
```

Restart the backend. The Library now lists videos from Drive, and every
submitted review is upserted into the Sheet (the header row is created
automatically on first write).

> If you prefer OAuth user credentials or Workload Identity instead of a
> service-account key, leave `GOOGLE_CREDENTIALS_FILE` blank and the app uses
> Application Default Credentials (`gcloud auth application-default login`).

---

## Enabling AI analysis

Set an Anthropic API key in `backend/.env`:

```ini
ANTHROPIC_API_KEY=sk-ant-...
AI_MODEL=claude-sonnet-4-6     # vision-capable; configurable
AI_MAX_FRAMES=8                # hard cap on frames sent per video
ENABLE_AI=true
```

With a key set, the analysis endpoint sends a small, defect-focused set of
frames to Claude for a structured verdict on text readability, logo
visibility, visual clarity, and an overall score. Without a key, the app
stays fully functional using the local OpenCV heuristics only.

### Per-video AI toggle

The Review Workspace has a **"Use AI semantic analysis"** toggle, off by
default. With it off, **Run analysis** performs only the local OpenCV
detection (blur / black / frozen) — free, no API call. Toggle it on (per
video) to add the paid Claude vision pass for that run. If no key is
configured server-side, the toggle is disabled and labelled *AI unavailable*,
so the UI never implies spend that can't happen. Under the hood this maps to
`POST /api/analysis/{id}?use_ai=true|false`; the response includes
`ai_requested` and `ai.ai_used` so you always know what actually ran.

---

## How the analysis works

**Intelligent sampling** (`frame_sampler.py`) — instead of decoding every
frame, it lays down a uniform baseline grid across the timeline and adds
extra samples at moments of high change (scene cuts) or suspiciously low
change (possible freezes) found by a cheap downscaled scan. This keeps
analysis cost roughly constant for short clips and multi-hour videos alike.

**Local defect heuristics** (`video_analysis.py`), all CPU-only:

| Defect | Method | Threshold (tunable) |
|---|---|---|
| Blurry | variance of the Laplacian (focus measure) | `< 100` |
| Black | mean luminance | `< 16/255` |
| Blank | luminance std-dev | `< 8` |
| Frozen / duplicate | mean abs diff vs previous sample | `< 0.15` |

Each finding carries a frame index, timestamp, severity, and message, so the
UI can render clickable, timestamp-anchored issues.

**AI layer** (`ai_service.py`) handles the semantic checks heuristics can't:
is on-screen text actually readable, is the brand logo present and clear.

Detected defects are mapped to a **suggested checklist** and a **suggested
outcome** (pass / review / fail), which pre-fill the reviewer's form.

---

## API reference

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Backend status, storage backend, AI on/off |
| GET | `/api/videos` | List videos. `?folder=<drive link/id>` to load a folder |
| GET | `/api/videos/{id}/stream` | Stream/preview a video (range-enabled) |
| POST | `/api/analysis/{id}` | Run analysis. `?use_ai=true` adds the paid Claude pass (default `false` = local only); `?force=true` recomputes |
| GET | `/api/analysis/{id}` | Cached analysis result |
| POST | `/api/batch` | Start a folder/multi-video batch review (body: `folder` or `video_ids`, `use_ai`) |
| GET | `/api/batch/{job_id}` | Batch job progress + per-video results |
| GET | `/api/reports/{id}.pdf` | Download a per-video PDF report (`?use_ai=`) |
| GET | `/api/reviews` | List all review records |
| POST | `/api/reviews` | Submit/upsert a review |
| GET | `/api/reviews/export.csv` | Export all reviews as CSV |
| GET | `/api/dashboard` | Aggregate analytics |

Interactive docs at <http://localhost:8000/docs> when the backend is running.

---

## Deploying to your git

```bash
cd video-audit-platform
git init
git add .
git commit -m "Initial commit: AI video audit & QA platform"

# GitLab
git remote add origin git@gitlab.com:<you>/video-audit-platform.git
git push -u origin main
```

CI is pre-configured for both hosts: `.gitlab-ci.yml` (runs backend tests and
the frontend build; a commented-out job builds & pushes container images on
tags) and `.github/workflows/ci.yml` (the GitHub Actions equivalent). Secrets
and `backend/data/` are git-ignored.

For container deployment, push the two images built by `docker-compose` to
your registry and run them behind the included nginx config (or any ingress).

---

## Extending the platform

The codebase is structured so the planned enhancements are additive:

- **Multi-reviewer collaboration** — `reviewer` is already a field; add auth
  and per-reviewer rows / agreement scoring in the Sheets schema.
- **Timestamp-based issue highlighting** — findings already carry timestamps;
  render them as markers on the scrubber track.
- **Advanced logo detection** — add a detector in `video_analysis.py` (e.g.
  template matching or a small model) and surface it like the other defects.
- **Automated audio quality analysis** — add an `audio_analysis.py` service
  (ffmpeg/librosa) and a new checklist mapping for `audio_sync`.
- **Cloud deployment** — Dockerfiles + compose are included; swap the storage
  backend for managed services via a new `Repository` subclass.
- **AI scoring systems** — the AI score (0–100) is already plumbed end to end;
  extend the prompt/schema for category sub-scores.

---

## Project layout

```
video-audit-platform/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app + CORS + routers
│   │   ├── config.py            env-driven settings
│   │   ├── models/schemas.py    Pydantic models
│   │   ├── routers/             videos · analysis · reviews · dashboard
│   │   └── services/
│   │       ├── frame_sampler.py     intelligent sampling
│   │       ├── video_analysis.py    OpenCV defect heuristics
│   │       ├── ai_service.py        Claude vision (optional)
│   │       ├── drive_service.py     Google Drive
│   │       ├── sheets_service.py    Google Sheets
│   │       └── storage.py           Repository abstraction
│   ├── scripts/make_sample_videos.py
│   ├── tests/test_analysis.py
│   ├── requirements.txt · Dockerfile · .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api/client.js
│   │   ├── components/   Dashboard · VideoLibrary · ReviewWorkspace
│   │   └── styles/index.css
│   ├── package.json · vite.config.js · Dockerfile · nginx.conf
├── docker-compose.yml
├── .github/workflows/ci.yml
├── .gitlab-ci.yml
└── .gitignore
```

---

## License

Add a license of your choice (MIT recommended for internal tooling) before
publishing.
