"use client";
import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { Radio, Wifi } from "lucide-react";
import { apiRequest, Camera, CameraAnalytics, VMSSystem } from "@/lib/api";
import { PreparedReplay } from "./PreparedReplay";

function Tile({ camera, systems, token }: { camera: Camera; systems: VMSSystem[]; token: string }) {
  const video = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [playing, setPlaying] = useState(true);
  const [analytics, setAnalytics] = useState<CameraAnalytics | null>(null);
  const [runtime, setRuntime] = useState<{ frame: number; detection_frame?: number | null; source_timestamp?: number | null; detection_age_ms?: number | null; people: number | null; vehicles: number | null; cars: number | null; motorcycles: number | null; buses: number | null; trucks: number | null; plates?: Array<{ text: string; confidence: number }>; unique_people?: number; unique_car?: number; unique_motorcycle?: number; unique_bus?: number; unique_truck?: number; status: string; model?: string; source_fps?: number; preview_fps?: number; ai_fps?: number; ai_frames?: number; inference_ms?: number; tracker_latency_ms?: number; queue_depth?: number; frames_processed?: number; displayed_frame_index?: number; device?: string; frame_drops?: number; playback_drops?: number; tracker?: Record<string, number>; objects?: Array<{ class: string; id: number | null; confidence: number }> } | null>(null);
  const [showAnnotations, setShowAnnotations] = useState(true);
  const [showTrackIds, setShowTrackIds] = useState(true);
  const [showPerformance, setShowPerformance] = useState(false);
  const developerMode = process.env.NODE_ENV !== "production";
  const source = camera.protocol === "MP4" || camera.protocol === "HLS" ? camera.source_url
    : camera.source_url.startsWith("rtsp://mediamtx:8554/") ? `http://localhost:8888/${camera.source_url.split("/").pop()}/index.m3u8` : "";
  const preview = camera.is_demo && camera.protocol === "MP4" && /\/demo-media\/(?:anpr-vms-[ab]|OP)\.mp4$/.test(source);
  useEffect(() => {
    if (!video.current || !source || failed) return;
    if (camera.protocol === "MP4" || video.current.canPlayType("application/vnd.apple.mpegurl")) {
      video.current.src = source; return;
    }
    if (!Hls.isSupported()) { setFailed(true); return; }
    const hls = new Hls();
    hls.loadSource(source); hls.attachMedia(video.current);
    hls.on(Hls.Events.ERROR, (_, data) => { if (data.fatal) setFailed(true); });
    return () => hls.destroy();
  }, [source, camera.protocol, failed]);
  useEffect(() => { let active = true; apiRequest<CameraAnalytics>(`/analytics/cameras/${camera.id}`, token).then(value => { if (active) setAnalytics(value); }).catch(() => undefined); return () => { active = false; }; }, [camera.id, token]);
  useEffect(() => {
    if (!preview) return;
    let active = true;
    let timer: number | undefined;
    let controller: AbortController | undefined;
    const poll = async () => {
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller?.abort(), 2000);
      try {
        const value = await apiRequest<typeof runtime>(`${new URL(source).pathname}/runtime`, undefined, { signal: controller.signal, cache: "no-store" });
        if (active) setRuntime(value);
      } catch {
        if (active) setRuntime(previous => previous ? { ...previous, status: "DISCONNECTED", people: null, vehicles: null, cars: null, motorcycles: null, buses: null, trucks: null, plates: [] } : null);
      } finally {
        window.clearTimeout(timeout);
        if (active) timer = window.setTimeout(poll, 300);
      }
    };
    void poll();
    return () => { active = false; window.clearTimeout(timer); controller?.abort(); };
  }, [preview, source]);
  return <article className="viewerTile">
    <div className="streamFrame">
      {preview && !previewFailed ? <>
        {/* The annotated multipart stream is the single YOLO/ByteTrack inference path. */}
        {playing ? <img className={showAnnotations ? "annotatedPreview" : ""} src={`${source}/preview?annotations=${showAnnotations ? "true" : "false"}&track_ids=${showTrackIds ? "true" : "false"}`} alt={`${camera.name} YOLO annotated recorded frames`} onError={() => setPreviewFailed(true)} /> : <p className="previewPaused">Recorded preview paused</p>}
        <div className="viewerControls">
          <button className="secondaryButton" onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Resume"} recorded preview</button>
          <label><input type="checkbox" checked={showAnnotations} onChange={event => setShowAnnotations(event.target.checked)} /> Show AI annotations</label>
          <label><input type="checkbox" checked={showTrackIds} onChange={event => setShowTrackIds(event.target.checked)} /> Track IDs</label>
          {developerMode ? <label><input type="checkbox" checked={showPerformance} onChange={event => setShowPerformance(event.target.checked)} /> Developer diagnostics</label> : null}
        </div>
        <small>OpenCV + {runtime?.model ?? "local detector"} + timestamp-aware tracking · {runtime?.status ?? "STARTING"} · IDs are anonymous and session-local</small>
        {developerMode && showPerformance && runtime ? <div className="developerOverlay" aria-label="Developer tracking diagnostics">
          <b>FRAME {runtime.detection_frame ?? "—"}</b>
          <span>SOURCE {formatSourceTime(runtime.source_timestamp)} · {runtime.source_fps ?? 0} FPS</span>
          <span>PROCESSING {runtime.ai_fps ?? 0} FPS · DETECTOR {runtime.inference_ms ?? 0} ms · TRACKER {runtime.tracker_latency_ms ?? "—"} ms · AGE {runtime.detection_age_ms ?? 0} ms</span>
          <span>DETECTIONS {(runtime.tracker?.detector_high ?? 0) + (runtime.tracker?.detector_low ?? 0)} · CONFIRMED {runtime.tracker?.visible ?? 0} · LOST {runtime.tracker?.lost ?? "—"} · NEW {runtime.tracker?.created ?? 0}</span>
          <span>QUEUE {runtime.queue_depth ?? "—"} · DROPPED {runtime.frame_drops ?? 0}/{runtime.playback_drops ?? 0} · PROCESSED {runtime.frames_processed ?? runtime.ai_frames ?? "—"}</span>
          <span>SOURCE FRAME {runtime.detection_frame ?? "—"} · DISPLAYED FRAME {runtime.displayed_frame_index ?? runtime.frame} · {runtime.device ?? "CPU"}</span>
          {runtime.objects?.map((object, index) => <span key={`${object.id ?? "unmatched"}-${index}`}>{object.class} #{object.id ?? "—"} · state={object.id == null ? "NEW" : "CONFIRMED"} · confidence={object.confidence.toFixed(2)} · age=— · missed=0 · velocity=—</span>)}
        </div> : null}
      </> : !failed && source ? <video ref={video} controls muted autoPlay loop playsInline onError={() => setFailed(true)} aria-label={`${camera.name} recorded source`} />
        : <div className="streamUnavailable"><Wifi /><strong>SOURCE UNAVAILABLE</strong><span>{source || "No browser-compatible endpoint"}</span></div>}
      <small>{camera.is_demo ? "DEMO RECORDED CCTV SOURCE" : camera.protocol} · {systems.find(v => v.id === camera.vms_system_id)?.name}</small>
      {runtime ? <div className="analyticsOverlay"><b>LATEST DETECTION · FRAME {runtime.detection_frame ?? "—"}</b><span>People {runtime.people ?? "—"}</span><span>Vehicles {runtime.vehicles ?? "—"}</span><span>{runtime.cars ?? "—"} cars · {runtime.motorcycles ?? "—"} motorcycles</span><em>{runtime.status === "TRACKING" ? `Observation ${(Number(runtime.detection_age_ms ?? 0) / 1000).toFixed(1)}s ago · includes parked vehicles` : "Waiting for a fresh observation"}</em>{runtime.plates?.length ? <em>LAST OCR: {runtime.plates.map((plate) => `${plate.text} (${Math.round(plate.confidence * 100)}%)`).join(" · ")}</em> : <em>LAST OCR: no readable plate yet</em>}<em>TRACKS THIS REPLAY: {runtime.unique_people ?? 0} people · {(runtime.unique_car ?? 0) + (runtime.unique_motorcycle ?? 0) + (runtime.unique_bus ?? 0) + (runtime.unique_truck ?? 0)} vehicles observed</em></div> : analytics ? <div className="analyticsOverlay"><b>TRACKING ACTIVE</b><span>People {analytics.current.people}</span><span>Vehicles {analytics.current.vehicles}</span><span>{analytics.traffic_state} traffic</span></div> : null}
    </div>
    <footer><strong>{camera.name}</strong><span className={`statusTag ${camera.health_status.toLowerCase()}`}>{camera.health_status}</span></footer>
  </article>;
}

function formatSourceTime(seconds?: number | null) {
  if (seconds == null) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}

export function RecordedViewer({ cameras, systems, token }: { cameras: Camera[]; systems: VMSSystem[]; token: string }) {
  return <div className="pageStack"><div className="noticeStrip"><Radio size={17}/><span><strong>LOCAL CAMERA SOURCES.</strong> AI processing runs on local recorded videos, including the user-provided OP.mp4 source.</span></div>
    <div className="viewerGrid">{cameras.slice(0, 4).map(camera => camera.source_url.endsWith('/demo-media/OP.mp4') ? <PreparedReplay key={camera.id} camera={camera}/> : <Tile key={camera.id} camera={camera} systems={systems} token={token}/>)}</div>
    {!cameras.length && <p>No camera sources returned by the API.</p>}
  </div>;
}
