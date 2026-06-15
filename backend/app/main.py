"""FastAPI application entrypoint for the Video Audit & Quality Review API."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ensure_dirs, get_settings
from .routers import analysis, batch, dashboard, reports, reviews, videos

settings = get_settings()
ensure_dirs(settings)

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router)
app.include_router(analysis.router)
app.include_router(batch.router)
app.include_router(reports.router)
app.include_router(reviews.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "storage_backend": settings.storage_backend,
        "ai_enabled": settings.enable_ai and bool(settings.anthropic_api_key),
        "ai_model": settings.ai_model,
    }
