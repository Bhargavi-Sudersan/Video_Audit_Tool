// Thin wrapper around the backend REST API. All paths are proxied to the
// FastAPI server (see vite.config.js / nginx.conf).
const json = (r) => {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
};

export const api = {
  health: () => fetch("/api/health").then(json),
  listVideos: (folder) =>
    fetch("/api/videos" + (folder ? `?folder=${encodeURIComponent(folder)}` : "")).then(json),
  streamUrl: (id) => `/api/videos/${encodeURIComponent(id)}/stream`,

  analyze: (id, { force = false, useAi = false } = {}) =>
    fetch(
      `/api/analysis/${encodeURIComponent(id)}?use_ai=${useAi}&force=${force}`,
      { method: "POST" }
    ).then(json),
  getAnalysis: (id) =>
    fetch(`/api/analysis/${encodeURIComponent(id)}`).then((r) => (r.ok ? r.json() : null)),

  startBatch: (payload) =>
    fetch("/api/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(json),
  getBatch: (jobId) => fetch(`/api/batch/${jobId}`).then(json),

  reportUrl: (id, useAi = false) =>
    `/api/reports/${encodeURIComponent(id)}.pdf?use_ai=${useAi}`,

  listReviews: () => fetch("/api/reviews").then(json),
  submitReview: (payload) =>
    fetch("/api/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(json),
  exportUrl: () => "/api/reviews/export.csv",

  dashboard: () => fetch("/api/dashboard").then(json),
};
