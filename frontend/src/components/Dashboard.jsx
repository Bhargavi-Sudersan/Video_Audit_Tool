import { useEffect, useState } from "react";
import { api } from "../api/client.js";

function Metric({ label, value, sub, tone }) {
  return (
    <div className="card metric">
      <div className="label">{label}</div>
      <div className={`value ${tone || ""}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export default function Dashboard({ onOpen }) {
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.dashboard().then(setStats).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="empty">Could not load dashboard: {err}</div>;
  if (!stats) return <div className="empty"><span className="spinner" /> Loading analytics…</div>;

  return (
    <div>
      <div className="grid metrics">
        <Metric label="Total Videos" value={stats.total_videos} sub="in repository" />
        <Metric label="Reviewed" value={stats.reviewed_videos}
          sub={`${stats.completion_pct}% complete`} tone="pass" />
        <Metric label="Passed" value={stats.passed} tone="pass" />
        <Metric label="Failed" value={stats.failed} tone="fail" />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="row between" style={{ marginBottom: 12 }}>
          <strong>Review completion</strong>
          <span className="mono muted">{stats.reviewed_videos}/{stats.total_videos}</span>
        </div>
        <div className="progress"><span style={{ width: `${stats.completion_pct}%` }} /></div>
        <div className="row" style={{ gap: 18, marginTop: 14 }}>
          <span className="badge pass">{stats.passed} pass</span>
          <span className="badge fail">{stats.failed} fail</span>
          <span className="badge review">{stats.needs_review} needs review</span>
        </div>
      </div>

      <div className="section-title">Recent reviews</div>
      <div className="card" style={{ padding: 0 }}>
        {stats.recent.length === 0 ? (
          <div className="empty">No reviews submitted yet.</div>
        ) : (
          <table>
            <thead>
              <tr><th>Video</th><th>Reviewer</th><th>Outcome</th><th>Score</th><th>Updated</th><th /></tr>
            </thead>
            <tbody>
              {stats.recent.map((r) => (
                <tr key={r.video_id + r.updated_at}>
                  <td>{r.video_name}</td>
                  <td className="muted">{r.reviewer}</td>
                  <td><span className={`badge ${r.outcome === "pass" ? "pass" : r.outcome === "fail" ? "fail" : "review"}`}>{r.outcome}</span></td>
                  <td className="mono">{r.score ?? "—"}</td>
                  <td className="mono muted">{new Date(r.updated_at).toLocaleString()}</td>
                  <td><button className="btn sm ghost" onClick={() => onOpen(r.video_id)}>open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
