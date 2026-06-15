"""In-process batch review jobs with progress tracking.

Reviews a list of videos (or a whole Drive folder) end to end: for each
video it runs the analysis, derives a suggested outcome, and saves a review
record to the central store. Progress is pollable while it runs.

This intentionally uses a simple thread + in-memory registry (no Celery /
Redis) to stay dependency-light and runnable anywhere. The ``JobStore``
boundary makes it straightforward to swap in a real queue later.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from ..config import Settings
from ..models.schemas import ReviewRecord, ReviewStatus
from .analysis_runner import run_full_analysis
from .storage import get_repository


@dataclass
class BatchItemResult:
    video_id: str
    video_name: str
    status: str = "pending"        # pending | done | error
    outcome: str | None = None
    score: int | None = None
    defect_counts: dict | None = None
    error: str | None = None


@dataclass
class BatchJob:
    id: str
    total: int
    use_ai: bool
    status: str = "queued"          # queued | running | completed | error
    done: int = 0
    current: str | None = None
    started_at: str = ""
    finished_at: str = ""
    items: list[BatchItemResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


_jobs: dict[str, BatchJob] = {}
_lock = threading.Lock()


def get_job(job_id: str) -> BatchJob | None:
    with _lock:
        return _jobs.get(job_id)


def start_batch(video_items: list[dict], use_ai: bool, settings: Settings) -> BatchJob:
    job = BatchJob(
        id=uuid.uuid4().hex[:12],
        total=len(video_items),
        use_ai=use_ai,
        items=[BatchItemResult(v["id"], v["name"]) for v in video_items],
    )
    with _lock:
        _jobs[job.id] = job

    thread = threading.Thread(
        target=_run, args=(job, video_items, use_ai, settings), daemon=True
    )
    thread.start()
    return job


def _run(job: BatchJob, video_items: list[dict], use_ai: bool, settings: Settings) -> None:
    job.status = "running"
    job.started_at = datetime.now(timezone.utc).isoformat()
    repo = get_repository(settings)

    for i, v in enumerate(video_items):
        job.current = v["name"]
        item = job.items[i]
        try:
            payload, _ = run_full_analysis(v["id"], use_ai, settings)
            outcome = payload.get("suggested_outcome", "review")
            score = payload.get("score")

            # Persist an automated review record centrally.
            record = ReviewRecord(
                video_id=v["id"],
                video_name=v["name"],
                reviewer="auto-batch",
                outcome=outcome,
                status=ReviewStatus.completed,
                checklist=[],
                comments=[],
                ai_summary=payload.get("ai", {}).get("summary", ""),
                score=score,
            )
            repo.save_review(record)

            item.status = "done"
            item.outcome = outcome
            item.score = score
            item.defect_counts = payload.get("defect_counts", {})
        except Exception as exc:  # keep the batch going on a single failure
            item.status = "error"
            item.error = str(exc)
        finally:
            job.done += 1

    job.current = None
    job.status = "completed"
    job.finished_at = datetime.now(timezone.utc).isoformat()
