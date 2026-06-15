import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client.js";

const CHECKLIST = [
  { key: "audio_sync", label: "Audio synchronization" },
  { key: "logo_visibility", label: "Logo visibility" },
  { key: "text_readability", label: "Text readability" },
  { key: "dropped_or_frozen_frames", label: "Dropped or frozen frames" },
  { key: "black_or_blank_frames", label: "Black / blank frames" },
  { key: "visual_clarity", label: "Visual clarity (no blur)" },
];
const OPTS = ["pass", "review", "fail"];
const FPS_FALLBACK = 30;

function fmtTime(t) {
  if (t == null || isNaN(t)) return "0:00.0";
  const m = Math.floor(t / 60);
  const s = (t % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

export default function ReviewWorkspace({ videoId, aiAvailable = false, onSubmitted }) {
  const videoRef = useRef(null);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [useAi, setUseAi] = useState(false); // off by default — protects token spend

  const [checklist, setChecklist] = useState(
    Object.fromEntries(CHECKLIST.map((c) => [c.key, "review"]))
  );
  const [comments, setComments] = useState([]);
  const [draft, setDraft] = useState("");
  const [outcome, setOutcome] = useState("review");
  const [reviewer, setReviewer] = useState("reviewer");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const fps = analysis?.fps && analysis.fps > 0 ? analysis.fps : FPS_FALLBACK;
  const src = api.streamUrl(videoId);

  // Load any cached analysis when the video changes.
  useEffect(() => {
    setAnalysis(null); setSaved(false); setComments([]);
    setChecklist(Object.fromEntries(CHECKLIST.map((c) => [c.key, "review"])));
    api.getAnalysis(videoId).then((a) => { if (a) applyAnalysis(a); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  function applyAnalysis(a) {
    setAnalysis(a);
    const sc = a.suggested_checklist || {};
    setChecklist((prev) => {
      const next = { ...prev };
      for (const c of CHECKLIST) if (sc[c.key]) next[c.key] = sc[c.key];
      return next;
    });
    if (a.suggested_outcome) setOutcome(a.suggested_outcome);
  }

  async function runAnalysis() {
    setAnalyzing(true);
    try {
      const a = await api.analyze(videoId, { force: true, useAi: useAi && aiAvailable });
      applyAnalysis(a);
    } catch (e) {
      alert("Analysis failed: " + e.message);
    } finally {
      setAnalyzing(false);
    }
  }

  function seek(t) {
    const v = videoRef.current;
    if (v) { v.currentTime = t; v.pause(); }
  }
  function step(frames) {
    const v = videoRef.current;
    if (v) { v.pause(); v.currentTime = Math.max(0, v.currentTime + frames / fps); }
  }

  function addComment() {
    if (!draft.trim()) return;
    setComments((c) => [...c, { text: draft.trim(), timestamp_sec: Number(time.toFixed(2)) }]);
    setDraft("");
  }

  async function submit() {
    setSaving(true);
    try {
      const payload = {
        video_id: videoId,
        video_name: videoId,
        reviewer,
        outcome,
        checklist: CHECKLIST.map((c) => ({ key: c.key, label: c.label, status: checklist[c.key], note: "" })),
        comments,
        ai_summary: analysis?.ai?.summary || "",
        score: analysis?.score ?? null,
      };
      await api.submitReview(payload);
      setSaved(true);
      onSubmitted && onSubmitted();
    } catch (e) {
      alert("Submit failed: " + e.message);
    } finally {
      setSaving(false);
    }
  }

  const findings = analysis?.findings || [];
  const aiNotes = analysis?.ai?.frame_notes || [];

  return (
    <div className="workspace">
      {/* LEFT: player + AI findings */}
      <div>
        <div className="card">
          <video
            ref={videoRef}
            src={src}
            controls
            onTimeUpdate={(e) => setTime(e.target.currentTime)}
            onLoadedMetadata={(e) => setDuration(e.target.duration)}
          />
          <div className="scrubber">
            <span className="timecode">{fmtTime(time)} / {fmtTime(duration)}</span>
            <input type="range" min={0} max={duration || 0} step={0.05}
              value={time} onChange={(e) => seek(Number(e.target.value))} />
          </div>
          <div className="frame-nav">
            <button className="btn sm" onClick={() => step(-10)}>⏮ 10f</button>
            <button className="btn sm" onClick={() => step(-1)}>◀ frame</button>
            <button className="btn sm" onClick={() => step(1)}>frame ▶</button>
            <button className="btn sm" onClick={() => step(10)}>10f ⏭</button>
            <span className="timecode" style={{ marginLeft: "auto" }}>
              {fps.toFixed(0)} fps · {analysis ? `${analysis.resolution}` : "—"}
            </span>
          </div>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <div className="row between" style={{ marginBottom: 10 }}>
            <strong>AI defect detection</strong>
            <div className="row" style={{ gap: 8 }}>
              <a className="btn sm ghost" href={api.reportUrl(videoId, useAi && aiAvailable)}
                target="_blank" rel="noreferrer">Download PDF</a>
              <button className="btn primary sm" onClick={runAnalysis} disabled={analyzing}>
                {analyzing ? <><span className="spinner" /> analyzing…</> : "Run analysis"}
              </button>
            </div>
          </div>

          <div className="row between" style={{ marginBottom: 10 }}>
            <label
              className={`toggle ${useAi && aiAvailable ? "on" : ""} ${aiAvailable ? "" : "disabled"}`}
              title={aiAvailable ? "" : "No API key configured on the server — local detection only."}
            >
              <span className="track" onClick={() => aiAvailable && setUseAi((v) => !v)}>
                <span className="knob" />
              </span>
              <span onClick={() => aiAvailable && setUseAi((v) => !v)}>
                Use AI semantic analysis
              </span>
            </label>
            <span className="mono muted" style={{ fontSize: 11 }}>
              {aiAvailable
                ? (useAi ? "AI ON · consumes API credits" : "local only · free")
                : "AI unavailable (no key)"}
            </span>
          </div>
          <div className="cost-note">
            {useAi && aiAvailable
              ? `Sends up to a few sampled frames to Claude for text / logo / clarity verdicts.`
              : `Blur, black & frozen-frame detection runs locally at no cost. Toggle on for AI checks of text readability & logo.`}
          </div>

          {!analysis && !analyzing && (
            <p className="muted" style={{ fontSize: 13 }}>
              Run analysis to intelligently sample frames and detect blurry, black,
              frozen/duplicate, and unreadable-text issues. Results pre-fill the checklist below.
            </p>
          )}

          {analysis && (
            <>
              <div className="row" style={{ gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
                <span className="mono muted">{analysis.sampled_frames} frames sampled of {analysis.total_frames}</span>
                {Object.entries(analysis.defect_counts).map(([k, n]) => (
                  <span key={k} className="badge fail">{n} {k.replace(/_/g, " ")}</span>
                ))}
                {findings.length === 0 && <span className="badge pass">no defects detected</span>}
                {analysis.score != null && <span className="mono">score {analysis.score}/100</span>}
              </div>

              <div style={{ fontSize: 13, padding: "8px 0", color: "var(--muted)" }}>
                {analysis.ai?.summary}
              </div>

              <div style={{ maxHeight: 220, overflow: "auto" }}>
                {findings.slice(0, 60).map((f, i) => (
                  <div className="ai-finding" key={i}>
                    <span className="tc" onClick={() => seek(f.timestamp)}>{fmtTime(f.timestamp)}</span>
                    <span className={`sev ${f.severity}`}>{f.severity}</span>
                    <span>{f.message}</span>
                  </div>
                ))}
                {aiNotes.map((n, i) => (
                  <div className="ai-finding" key={"ai" + i}>
                    <span className="sev low">AI</span>
                    <span>frame {n.frame}: {n.note}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* RIGHT: checklist + comments + submit */}
      <div>
        <div className="card">
          <strong>Review checklist</strong>
          <div style={{ marginTop: 8 }}>
            {CHECKLIST.map((c) => (
              <div className="checklist-row" key={c.key}>
                <span className="clabel">{c.label}</span>
                <div className="seg">
                  {OPTS.map((o) => (
                    <button key={o}
                      className={checklist[c.key] === o ? `on ${o}` : ""}
                      onClick={() => setChecklist((p) => ({ ...p, [c.key]: o }))}>
                      {o}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <strong>Comments</strong>
          <div className="row" style={{ marginTop: 10, gap: 8 }}>
            <input type="text" placeholder={`Note at ${fmtTime(time)}…`}
              value={draft} onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addComment()} />
            <button className="btn sm" onClick={addComment}>Add</button>
          </div>
          {comments.map((c, i) => (
            <div className="comment" key={i}>
              {c.timestamp_sec != null && (
                <span className="tc" onClick={() => seek(c.timestamp_sec)}>{fmtTime(c.timestamp_sec)} </span>
              )}
              {c.text}
            </div>
          ))}
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <div className="row between" style={{ marginBottom: 10 }}>
            <strong>Evaluation</strong>
            <div className="seg">
              {OPTS.map((o) => (
                <button key={o} className={outcome === o ? `on ${o}` : ""} onClick={() => setOutcome(o)}>{o}</button>
              ))}
            </div>
          </div>
          <div className="row" style={{ gap: 8, marginBottom: 12 }}>
            <span className="muted" style={{ fontSize: 12 }}>Reviewer</span>
            <input type="text" value={reviewer} onChange={(e) => setReviewer(e.target.value)} style={{ maxWidth: 180 }} />
          </div>
          <button className="btn primary" style={{ width: "100%" }} onClick={submit} disabled={saving}>
            {saving ? <><span className="spinner" /> submitting…</> : saved ? "✓ Submitted — submit again" : "Submit evaluation"}
          </button>
          {saved && <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>Saved to central store.</div>}
        </div>
      </div>
    </div>
  );
}
