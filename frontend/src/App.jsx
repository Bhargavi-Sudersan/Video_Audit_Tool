import { useEffect, useState } from "react";
import { api } from "./api/client.js";
import Dashboard from "./components/Dashboard.jsx";
import VideoLibrary from "./components/VideoLibrary.jsx";
import ReviewWorkspace from "./components/ReviewWorkspace.jsx";

export default function App() {
  const [view, setView] = useState("dashboard"); // dashboard | library | review
  const [activeVideo, setActiveVideo] = useState(null);
  const [health, setHealth] = useState(null);

  useEffect(() => { api.health().then(setHealth).catch(() => setHealth({ status: "down" })); }, []);

  const openReview = (videoId) => { setActiveVideo(videoId); setView("review"); };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">QA</div>
          <div>
            <h1>Video Audit &amp; Quality Review</h1>
            <span>media QA workstation</span>
          </div>
        </div>
        <nav className="nav">
          <button className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}>Dashboard</button>
          <button className={view === "library" ? "active" : ""} onClick={() => setView("library")}>Library</button>
          <button className={view === "review" ? "active" : ""} onClick={() => setView("review")} disabled={!activeVideo}>Review</button>
          <a className="nav-link" href={api.exportUrl()} target="_blank" rel="noreferrer">
            <button>Export CSV</button>
          </a>
        </nav>
        <div className="status-pill">
          <span className={`dot ${health?.status === "ok" ? "" : "off"}`} />
          {health ? (
            <>backend {health.status} · {health.storage_backend} · AI {health.ai_enabled ? "on" : "off"}</>
          ) : "connecting…"}
        </div>
      </header>

      <main className="content">
        {view === "dashboard" && <Dashboard onOpen={openReview} />}
        {view === "library" && (
          <VideoLibrary
            onOpen={openReview}
            aiAvailable={!!health?.ai_enabled}
            demoMode={health?.storage_backend !== "google"}
          />
        )}
        {view === "review" && activeVideo && (
          <ReviewWorkspace
            videoId={activeVideo}
            aiAvailable={!!health?.ai_enabled}
            onSubmitted={() => {}}
          />
        )}
        {view === "review" && !activeVideo && (
          <div className="empty">Select a video from the Library to begin a review.</div>
        )}
      </main>
    </div>
  );
}
