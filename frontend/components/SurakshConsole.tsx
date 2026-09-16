"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Archive, BarChart3, Camera as CameraIcon, Database, FileText, Map, Radio, Search, Shield, Siren, Users, Wifi, X } from "lucide-react";
import { apiRequest, AnalyticsBucket, AnalyticsSummary, Camera, CameraAnalytics, Department, Detection, GapAnalysis, User, VMSSystem, Watchlist } from "@/lib/api";
import { AuditPanel, InvestigationPanel, LiveAlerts, WatchlistPanel, IntegrationPanel } from "./RuntimePanels";
import { RecordedViewer } from "./RecordedViewer";
import { RegistryPanel } from "./RegistryPanel";
import { ApiError } from "@/lib/api";

const GisMap = dynamic(() => import("@/components/GisMap").then((module) => module.GisMap), { ssr: false, loading: () => <div className="mapLoading">Loading Gujarat GIS…</div> });

export type View = "dashboard" | "registry" | "gis" | "viewer" | "analytics" | "investigations" | "watchlists" | "integrations" | "health" | "audit" | "settings" | "alerts";
type Session = { access_token: string; user: User };

const nav: Array<[View, string, typeof Shield]> = [
  ["dashboard", "Operations", Activity], ["registry", "CCTV Registry", Database], ["gis", "Gujarat GIS", Map], ["viewer", "Unified Viewer", Radio], ["investigations", "Investigations", Search], ["watchlists", "Watchlists", Siren], ["integrations", "Federation", Wifi], ["health", "Camera Health", CameraIcon], ["audit", "Audit Log", FileText], ["settings", "Settings", Shield]
];
nav.splice(4, 0, ["analytics", "Traffic Analytics", BarChart3]);
nav.splice(6, 0, ["alerts", "Alerts", Siren]);

export function SurakshConsole({ view }: { view: View }) {
  const [session, setSession] = useState<Session | null>(null);
  const [email, setEmail] = useState("admin@suraksh.demo");
  const [password, setPassword] = useState("Suraksh123!");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [vms, setVms] = useState<VMSSystem[]>([]);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [gap, setGap] = useState<GapAnalysis | null>(null);
  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null);

  useEffect(() => {
    const raw = window.localStorage.getItem("suraksh-session");
    if (raw) { try { setSession(JSON.parse(raw) as Session); } catch { window.localStorage.removeItem("suraksh-session"); } }
  }, []);

  useEffect(() => {
    if (!session) return;
    loadData(session.access_token);
  }, [session, view]);

  async function loadData(token: string) {
    setLoading(true); setError("");
    try {
      const [cameraData, departmentData, vmsData, detectionData, watchlistData, summaryData, gapData] = await Promise.all([
        apiRequest<Camera[]>("/cameras", token), apiRequest<Department[]>("/departments", token), apiRequest<VMSSystem[]>("/integrations/vms", token), apiRequest<Detection[]>("/detections", token), apiRequest<Watchlist[]>("/watchlists", token), apiRequest<Record<string, unknown>>("/analytics/summary", token), apiRequest<GapAnalysis>("/registry/summary", token)
      ]);
      setCameras(cameraData); setDepartments(departmentData); setVms(vmsData); setDetections(detectionData); setWatchlists(watchlistData); setSummary(summaryData); setGap(gapData);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        window.localStorage.removeItem("suraksh-session");
        setSession(null);
        setCameras([]); setDepartments([]); setVms([]); setDetections([]);
        setWatchlists([]); setSummary({}); setGap(null); setSelectedCamera(null);
        setError("Your session expired or is no longer valid. Please sign in again.");
        return;
      }
      setError(cause instanceof Error ? cause.message : "SURAKSH API unavailable. Retry when the services are running.");
    } finally { setLoading(false); }
  }

  async function login(event: React.FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try { const next = await apiRequest<Session>("/auth/login", undefined, { method: "POST", body: JSON.stringify({ email, password }) }); setSession(next); window.localStorage.setItem("suraksh-session", JSON.stringify(next)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Login failed"); }
    finally { setLoading(false); }
  }

  if (!session) return <LoginScreen email={email} password={password} setEmail={setEmail} setPassword={setPassword} onSubmit={login} loading={loading} error={error} />;

  return <main className="surakshApp">
    <aside className="surakshSidebar">
      <Link className="surakshBrand" href="/"><span className="brandMark">S</span><span><strong>SURAKSH</strong><small>Federating CCTV. Connecting Intelligence.</small></span></Link>
      <div className="demoBanner">HACKATHON DEMO<br /><span>All records are synthetic</span></div>
      <nav>{nav.map(([key, label, Icon]) => <a className={view === key ? "active" : ""} href={key === "dashboard" ? "/" : `/${key}`} key={key}><Icon size={17} />{label}</a>)}</nav>
      <button className="sidebarLogout" onClick={() => { window.localStorage.removeItem("suraksh-session"); setSession(null); }}><Archive size={16} /> Sign out</button>
    </aside>
    <section className="surakshMain">
      <header className="surakshTopbar"><div><span className="sectionKicker">GUJARAT POLICE HACKATHON 2026</span><h1>{nav.find(([key]) => key === view)?.[1] ?? "Operations"}</h1></div><div className="topbarMeta"><span className="statusDot">{error ? "API ERROR" : loading ? "CONNECTING" : "API CONNECTED"}</span><span>{session.user.name}</span></div></header>
      {error ? <div className="errorBanner"><AlertTriangle size={16} />{error}<button onClick={() => loadData(session.access_token)}><Wifi size={14} /> Retry</button></div> : null}
      {loading ? <div className="loadingBanner">Syncing registry and event metadata…</div> : null}
      {view === "dashboard" ? <Dashboard summary={summary} cameras={cameras} detections={detections} gap={gap} onCamera={setSelectedCamera} /> : null}
      {view === "registry" ? <RegistryPanel token={session.access_token} cameras={cameras} departments={departments} systems={vms} onCamera={setSelectedCamera} /> : null}
      {view === "gis" ? <GIS cameras={cameras} gap={gap} selected={selectedCamera} onCamera={setSelectedCamera} /> : null}
      {view === "viewer" ? <RecordedViewer cameras={cameras} systems={vms} token={session.access_token} /> : null}
      {view === "analytics" ? <AnalyticsPanel token={session.access_token} summary={summary as Partial<AnalyticsSummary>} cameras={cameras} /> : null}
      {view === "investigations" ? <InvestigationPanel token={session.access_token} /> : null}
      {view === "watchlists" ? <WatchlistPanel token={session.access_token} items={watchlists} departments={departments} refresh={() => void loadData(session.access_token)} /> : null}
      {view === "integrations" ? <IntegrationPanel token={session.access_token} systems={vms} refresh={() => void loadData(session.access_token)} /> : null}
      {view === "dashboard" || view === "alerts" ? <LiveAlerts token={session.access_token} /> : null}
      {view === "health" ? <Health cameras={cameras} /> : null}
      {view === "audit" ? <AuditPanel token={session.access_token} /> : null}
      {view === "settings" ? <Settings /> : null}
      {selectedCamera ? <CameraDrawer camera={selectedCamera} token={session.access_token} onClose={() => setSelectedCamera(null)} /> : null}
    </section>
  </main>;
}

function LoginScreen({ email, password, setEmail, setPassword, onSubmit, loading, error }: { email: string; password: string; setEmail: (v: string) => void; setPassword: (v: string) => void; onSubmit: (e: React.FormEvent) => void; loading: boolean; error: string }) {
  return <main className="loginScreen"><section className="loginCard"><span className="brandMark large">S</span><span className="sectionKicker">SECURE CONTROL ROOM</span><h1>SURAKSH</h1><p>Federating CCTV. Connecting Intelligence.</p><form onSubmit={onSubmit}><label>Operator email<input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required /></label><label>Password<input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required /></label>{error ? <div className="inlineError">{error}</div> : null}<button className="primaryButton" disabled={loading}>{loading ? "Authenticating…" : "Enter control room"}</button></form><small>Demo access is intentionally local and only available when the demo seed is enabled.</small></section></main>;
}

function AnalyticsPanel({ token, summary, cameras }: { token: string; summary: Partial<AnalyticsSummary>; cameras: Camera[] }) {
  const [buckets, setBuckets] = useState<AnalyticsBucket[]>([]);
  useEffect(() => { apiRequest<{ buckets: AnalyticsBucket[] }>("/analytics/timeseries", token).then(value => setBuckets(value.buckets)).catch(() => setBuckets([])); }, [token]);
  const latest = buckets.slice(-2);
  return <div className="pageStack"><div className="noticeStrip"><BarChart3 size={17}/><span><strong>Traffic &amp; Crowd Analytics.</strong> Anonymous YOLO track IDs, minute-bucketed; synthetic recorded CCTV only.</span></div><section className="metricGrid"><Metric label="People currently visible" value={summary.people_visible ?? 0} /><Metric label="Vehicles currently visible" value={summary.vehicles_visible ?? 0} tone="good" /><Metric label="Unique vehicle tracks" value={summary.unique_vehicles ?? 0} /><Metric label="Unique people tracks" value={summary.unique_people ?? 0} /></section><Panel title="Vehicle type breakdown" icon={<BarChart3 />}><div className="analyticsBreakdown"><Metric label="Cars observed" value={summary.cars ?? 0}/><Metric label="Motorcycles observed" value={summary.motorcycles ?? 0}/><Metric label="Buses observed" value={summary.buses ?? 0}/><Metric label="Trucks observed" value={summary.trucks ?? 0}/></div></Panel><Panel title="Camera buckets" icon={<CameraIcon />}><div className="tableWrap"><table><thead><tr><th>Camera</th><th>Bucket</th><th>People peak</th><th>Vehicles peak</th><th>Unique vehicles</th><th>Types</th></tr></thead><tbody>{latest.map(bucket => <tr key={bucket.id}><td>{cameras.find(camera => camera.id === bucket.camera_id)?.name ?? bucket.camera_id}</td><td>{new Date(bucket.bucket_start).toLocaleTimeString("en-IN")}</td><td>{bucket.people_visible_peak}</td><td>{bucket.vehicle_visible_peak}</td><td>{bucket.unique_vehicles}</td><td>{bucket.unique_cars} cars · {bucket.unique_motorcycles} motorcycles · {bucket.unique_buses} buses · {bucket.unique_trucks} trucks</td></tr>)}</tbody></table></div>{!latest.length ? <Empty text="No persisted analytics buckets yet."/> : null}</Panel></div>;
}

function Dashboard({ summary, cameras, detections, gap, onCamera }: { summary: Record<string, unknown>; cameras: Camera[]; detections: Detection[]; gap: GapAnalysis | null; onCamera: (c: Camera) => void }) {
  return <div className="pageStack"><div className="noticeStrip"><Shield size={17} /><span><strong>Federation layer active.</strong> SURAKSH preserves departmental VMS ownership and stores registry plus event metadata.</span></div><section className="metricGrid"><Metric label="Total cameras" value={String(summary.cameras_total ?? cameras.length)} /><Metric label="Online" value={String(summary.cameras_online ?? cameras.filter((c) => c.health_status === "ONLINE").length)} tone="good" /><Metric label="Active alerts" value={String(summary.active_alerts ?? 0)} tone="alert" /><Metric label="Departments" value={String(new Set(cameras.map((c) => c.department_id)).size)} /></section><Panel title="Traffic & Crowd Analytics" icon={<BarChart3 />}><div className="analyticsBreakdown"><Metric label="People visible" value={Number(summary.people_visible ?? 0)} /><Metric label="Vehicles visible" value={Number(summary.vehicles_visible ?? 0)} /><Metric label="Cars observed" value={Number(summary.cars ?? 0)} /><Metric label="Motorcycles observed" value={Number(summary.motorcycles ?? 0)} /><Metric label="Buses observed" value={Number(summary.buses ?? 0)} /><Metric label="Trucks observed" value={Number(summary.trucks ?? 0)} /></div><p className="syntheticNotice">Anonymous YOLO tracking · DEMO RECORDED CCTV SOURCE · approximate when IDs are recreated</p></Panel><div className="twoColumn"><Panel title="Camera registry health" icon={<CameraIcon />}><div className="cameraMiniGrid">{cameras.slice(0, 6).map((camera) => <button className="cameraMini" key={camera.id} onClick={() => onCamera(camera)}><span className={`healthIndicator ${camera.health_status.toLowerCase()}`} /><strong>{camera.name}</strong><small>{camera.district} · {camera.is_demo ? "DEMO" : "REGISTERED"}</small><em>{camera.health_status}</em></button>)}</div></Panel><Panel title="Recent vehicle detections" icon={<Siren />}><div>{detections.slice(-4).reverse().map(d => <article className="runtimeAlert" key={d.id}><strong>{d.plate_text ?? "Plate unreadable"}</strong><p>{d.camera_name} · {d.source_system}</p><small>YOLO {(d.vehicle_confidence * 100).toFixed(1)}% · OCR {((d.plate_confidence ?? 0) * 100).toFixed(1)}% · DEMO / SYNTHETIC</small></article>)}</div></Panel></div><div className="twoColumn"><Panel title="Coverage gap analysis" icon={<BarChart3 />}><p className="syntheticNotice">{gap?.synthetic_data_notice ?? "SYNTHETIC HACKATHON DEMO DATA"}</p>{gap ? <><div className="ratioRow"><Metric label="Online ratio" value={`${Math.round(gap.online_ratio * 100)}%`} tone="good" /><Metric label="Offline ratio" value={`${Math.round(gap.offline_ratio * 100)}%`} tone="alert" /><Metric label="Degraded ratio" value={`${Math.round(gap.degraded_ratio * 100)}%`} /></div><div className="districtRows">{Object.entries(gap.by_district).map(([district, count]) => <div key={district}><span>{district}</span><b>{count} cameras</b></div>)}</div></> : <Empty text="Gap analysis is unavailable." />}</Panel><Panel title="Operator handoff" icon={<FileText />}><div className="handoffList"><span><i>01</i>Confirm stream reachability</span><span><i>02</i>Review vehicle detections</span><span><i>03</i>Check active watchlists</span><span><i>04</i>Record actions in audit log</span></div></Panel></div></div>;
}

function GIS({ cameras, gap, selected, onCamera }: { cameras: Camera[]; gap: GapAnalysis | null; selected: Camera | null; onCamera: (c: Camera) => void }) { return <div className="pageStack"><div className="noticeStrip"><Map size={17} /><span><strong>Gujarat GIS registry.</strong> Markers are synthetic records for hackathon demonstration only.</span></div><section className="gisLayout"><div className="mapPanel"><GisMap cameras={cameras} onSelect={onCamera} /></div><Panel title="Registry coverage" icon={<BarChart3 />}><p className="syntheticNotice">{gap?.synthetic_data_notice}</p>{Object.entries(gap?.by_district ?? {}).map(([district, count]) => <div className="coverageRow" key={district}><span>{district}</span><b>{count}</b><i style={{ width: `${Math.min(count * 18, 100)}%` }} /></div>)}<div className="legend"><span><i className="online" /> Online</span><span><i className="offline" /> Offline</span><span><i className="degraded" /> Degraded</span></div></Panel></section></div>; }

function Health({ cameras }: { cameras: Camera[] }) { return <div className="pageStack"><Panel title="Camera Health" icon={<Activity />}><div className="healthGrid">{cameras.map((camera) => <article key={camera.id}><header><strong>{camera.name}</strong><span className={`statusTag ${camera.health_status.toLowerCase()}`}>{camera.health_status}</span></header><div className="healthFacts"><span>Last heartbeat <b>{new Date(camera.last_heartbeat).toLocaleString("en-IN")}</b></span><span>Stream <b>{camera.stream_status}</b></span><span>Protocol <b>{camera.protocol}</b></span><span>Nominal FPS <b>{camera.fps || "Unknown"}</b></span></div></article>)}</div></Panel></div>; }
function Settings() { return <div className="pageStack"><Panel title="System Settings" icon={<Shield />}><div className="settingsNotice"><Shield size={22} /><div><strong>Security boundary</strong><p>Connector secrets are machine-side credentials and are never returned to browser clients. Government integrations require official authorization.</p></div></div></Panel></div>; }

function CameraDrawer({ camera, token, onClose }: { camera: Camera; token: string; onClose: () => void }) { const [analytics, setAnalytics] = useState<CameraAnalytics | null>(null); useEffect(() => { apiRequest<CameraAnalytics>(`/analytics/cameras/${camera.id}`, token).then(setAnalytics).catch(() => setAnalytics(null)); }, [camera.id, token]); return <aside className="cameraDrawer"><header><div><span className="sectionKicker">CAMERA REGISTRY RECORD</span><h2>{camera.name}</h2></div><button onClick={onClose} aria-label="Close"><X size={18} /></button></header><dl><div><dt>External ID</dt><dd>{camera.external_id ?? camera.id}</dd></div><div><dt>Department / district</dt><dd>{camera.department_id ?? "Unassigned"} · {camera.district}</dd></div><div><dt>Location</dt><dd>{camera.latitude ?? "Unknown"}, {camera.longitude ?? "Unknown"} · {camera.zone}</dd></div><div><dt>Vendor / model</dt><dd>{camera.vendor} · {camera.model}</dd></div><div><dt>VMS / protocol</dt><dd>{camera.vms_system_id ?? "None"} · {camera.protocol}</dd></div><div><dt>Health</dt><dd><span className={`statusTag ${camera.health_status.toLowerCase()}`}>{camera.health_status}</span> · {new Date(camera.last_heartbeat).toLocaleString("en-IN")}</dd></div></dl>{analytics ? <Panel title="Current Scene" icon={<BarChart3 />}><div className="analyticsBreakdown"><Metric label="People" value={analytics.current.people}/><Metric label="Vehicles" value={analytics.current.vehicles}/></div><p className="syntheticNotice">Traffic state: {analytics.traffic_state}</p></Panel> : null}<div className="drawerActions"><Link className="secondaryButton" href="/viewer">Open viewer</Link><Link className="secondaryButton" href="/investigations">Detection history</Link></div></aside>; }

function Panel({ title, icon, action, children }: { title: string; icon: React.ReactNode; action?: React.ReactNode; children: React.ReactNode }) { return <section className="surakshPanel"><header className="panelHeader"><div>{icon}<h2>{title}</h2></div>{action}</header>{children}</section>; }
function Metric({ label, value, tone = "" }: { label: string; value: string | number; tone?: string }) { return <article className={`metric ${tone}`}><strong>{value}</strong><span>{label}</span></article>; }
function EventList({ events }: { events: Array<Record<string, unknown>> }) { return <div className="eventList">{events.map((event, index) => <article key={String(event.id ?? index)}><span className="eventGlyph"><AlertTriangle size={15} /></span><div><strong>{String(event.type ?? "Security event").replaceAll("_", " ")}</strong><span>{String(event.camera_name ?? event.camera_id ?? "Camera")}</span></div><b>{Math.round(Number(event.confidence ?? 0) * 100)}%</b></article>)}{!events.length ? <Empty text="No events returned by the API." /> : null}</div>; }
function Empty({ text }: { text: string }) { return <div className="emptyState"><Archive size={18} /><span>{text}</span></div>; }
