import { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";

function fmtSize(bytes) {
  if (!bytes) return "—";
  const mb = bytes / 1024 / 1024;
  return mb > 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(1)} MB`;
}

export default function VideoLibrary({ onOpen, aiAvailable = false, demoMode = true }) {
  const [folder, setFolder] = useState("");
  const [videos, setVideos] = useState(null);
  const [reviewed, setReviewed] = useState(new Set());
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [batchAi, setBatchAi] = useState(false);

  const [job, setJob] = useState(null);
  const pollRef = useRef(null);

  async function load(folderArg) {
    setLoading(true); setErr(null);
    try {
      const vids = await api.listVideos(folderArg);
      setVideos(vids);
      setSelected(new Set());
      const rs = await api.listReviews();
      setReviewed(new Set(rs.map((r) => r.video_id)));
    } catch (e) {
      setErr(e.message); setVideos([]);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); return () => clearInterval(pollRef.current); }, []);

  function toggle(id) {
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  async function startBatch(allOrSelected) {
    const payload = { use_ai: batchAi && aiAvailable };
    if (folder.trim()) payload.folder = folder.trim();
    if (allOrSelected === "selected") payload.video_ids = [...selected];
    try {
      const j = await api.startBatch(payload);
      setJob(j);
      clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        const st = await api.getBatch(j.id);
        setJob(st);
        if (st.status === "completed" || st.status === "error") {
          clearInterval(pollRef.current);
          const rs = await api.listReviews();
          setReviewed(new Set(rs.map((r) => r.video_id)));
        }
      }, 700);
    } catch (e) {
      alert("Batch failed: " + e.message);
    }
  }

  return (
    <div>
      {/* Connect bar */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row between" style={{ marginBottom: 8 }}>
          <strong>Source</strong>
          <span className="mono muted" style={{ fontSize: 11 }}>
            {demoMode ? "demo mode · local sample videos" : "google drive"}
          </span>
        </div>
        {demoMode ? (
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>
            Running in demo mode — sample videos load automatically. Switch the backend to
            <span className="mono"> STORAGE_BACKEND=google </span> to paste a Drive folder link here.
          </p>
        ) : (
          <div className="row" style={{ gap: 8 }}>
            <input type="text" placeholder="Paste a Google Drive folder link…"
              value={folder} onChange={(e) => setFolder(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load(folder.trim())} />
            <button className="btn" onClick={() => load(folder.trim())} disabled={loading}>
              {loading ? <span className="spinner" /> : "Load"}
            </button>
          </div>
        )}
        {!demoMode && (
          <div className="cost-note" style={{ marginTop: 6 }}>
            The folder must be shared with the service-account email (see README).
          </div>
        )}
      </div>

      {err && <div className="empty">Could not load videos: {err}</div>}
      {!videos && !err && <div className="empty"><span className="spinner" /> Connecting to repository…</div>}

      {videos && videos.length > 0 && (
        <>
          {/* Batch controls */}
          <div className="card" style={{ marginBottom: 14 }}>
            <div className="row between">
              <div className="row" style={{ gap: 14 }}>
                <span className="muted">{videos.length} videos · {reviewed.size} reviewed · {selected.size} selected</span>
                <label className={`toggle ${batchAi && aiAvailable ? "on" : ""} ${aiAvailable ? "" : "disabled"}`}>
                  <span className="track" onClick={() => aiAvailable && setBatchAi((v) => !v)}><span className="knob" /></span>
                  <span onClick={() => aiAvailable && setBatchAi((v) => !v)}>AI pass {aiAvailable ? "" : "(no key)"}</span>
                </label>
              </div>
              <div className="row" style={{ gap: 8 }}>
                <button className="btn sm" onClick={() => startBatch("selected")} disabled={!selected.size || job?.status === "running"}>
                  Review selected
                </button>
                <button className="btn primary sm" onClick={() => startBatch("all")} disabled={job?.status === "running"}>
                  Review all
                </button>
              </div>
            </div>

            {job && (
              <div style={{ marginTop: 14 }}>
                <div className="row between" style={{ marginBottom: 6 }}>
                  <span className="mono muted" style={{ fontSize: 12 }}>
                    {job.status === "running" ? `Reviewing: ${job.current || "…"}` : `Batch ${job.status}`}
                  </span>
                  <span className="mono muted" style={{ fontSize: 12 }}>{job.done}/{job.total}</span>
                </div>
                <div className="progress"><span style={{ width: `${job.total ? (job.done / job.total) * 100 : 0}%` }} /></div>
                {job.status === "completed" && (
                  <div style={{ marginTop: 12, maxHeight: 220, overflow: "auto" }}>
                    <table>
                      <thead><tr><th>Video</th><th>Outcome</th><th>Defects</th><th>Report</th></tr></thead>
                      <tbody>
                        {job.items.map((it) => (
                          <tr key={it.video_id}>
                            <td>{it.video_name}</td>
                            <td>{it.status === "error"
                              ? <span className="badge fail">error</span>
                              : <span className={`badge ${it.outcome === "pass" ? "pass" : it.outcome === "fail" ? "fail" : "review"}`}>{it.outcome}</span>}</td>
                            <td className="mono muted" style={{ fontSize: 12 }}>
                              {it.error ? it.error : Object.entries(it.defect_counts || {}).map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`).join(", ") || "none"}
                            </td>
                            <td>
                              {it.status === "done" && (
                                <a className="btn sm ghost" href={api.reportUrl(it.video_id, job.use_ai)} target="_blank" rel="noreferrer">PDF</a>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Video grid */}
          <div className="library">
            {videos.map((v) => (
              <div className="video-card" key={v.id}>
                <div className="row between">
                  <label className="row" style={{ gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={selected.has(v.id)} onChange={() => toggle(v.id)} />
                    <span className="name">{v.name}</span>
                  </label>
                  {reviewed.has(v.id) && <span className="badge pass">reviewed</span>}
                </div>
                <div className="meta">{v.source} · {fmtSize(v.size_bytes)}</div>
                <div className="actions">
                  <button className="btn primary sm" onClick={() => onOpen(v.id)}>Review</button>
                  <a className="btn sm ghost" href={api.reportUrl(v.id, false)} target="_blank" rel="noreferrer">Report PDF</a>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {videos && videos.length === 0 && !err && (
        <div className="empty">
          No videos found.<br />
          <span className="mono">{demoMode ? "Run scripts.make_sample_videos, then refresh." : "Check the folder link and sharing permissions."}</span>
        </div>
      )}
    </div>
  );
}
