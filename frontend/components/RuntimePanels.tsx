"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { apiRequest, Camera, Department, Detection, VMSSystem, Watchlist } from "@/lib/api";
import { RuntimeAlert, subscribeAlerts } from "@/lib/alert-stream";

const PathMap = dynamic(() => import("./ObservedPathMap"), { ssr: false });
export const timestamp = (value: string) => new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString("en-IN");

export function LiveAlerts({ token }: { token: string }) {
  const [alerts, setAlerts] = useState<RuntimeAlert[]>([]);
  const [connection, setConnection] = useState("CONNECTING");
  const [last, setLast] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => apiRequest<RuntimeAlert[]>("/alerts", token, { signal: controller.signal }).then(rows => setAlerts(old => {
      const merged = new Map([...rows, ...old].map(a => [a.id, a]));
      return Array.from(merged.values()).sort((a, b) => b.created_at.localeCompare(a.created_at));
    })).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    void refresh();
    void subscribeAlerts(token, controller.signal, alert => {
      setLast(alert.id); setAlerts(rows => [alert, ...rows.filter(a => a.id !== alert.id)].slice(0, 100));
    }, setConnection, () => { void refresh(); });
    return () => controller.abort();
  }, [token]);
  return <section className="surakshPanel runtimePanel" aria-live="polite" data-stream-state={connection} data-last-realtime-alert={last}>
    <h2>Watchlist Alerts</h2><p className="muted">SSE {connection} · {alerts.length} persisted alerts</p>
    {error && <p className="errorBanner">{error}</p>}
    {!alerts.length && <p className="emptyState">No watchlist alerts persisted yet.</p>}
    {alerts.slice(0, 5).map(a => <article className="runtimeAlert" key={a.id} data-alert-id={a.id}>
      <strong>{a.priority.toUpperCase()} PRIORITY · {a.plate_text ?? "Plate not read"}</strong>
      <p>{a.camera_name} · {a.department} · {a.source_system}</p>
      <p>{a.district} / {a.location} · {timestamp(a.detected_at)}</p>
      <p>YOLO {(a.vehicle_confidence * 100).toFixed(1)}% · OCR {((a.plate_confidence ?? 0) * 100).toFixed(1)}%</p>
      <small>{a.is_demo ? "DEMO / SYNTHETIC INPUT" : "Recorded observation"} · Alert {a.id}</small>
      {last === a.id && <p className="liveArrival">Received automatically via SSE</p>}
    </article>)}
  </section>;
}

type PathResult = { label: string; plate: string; points: Detection[]; missing_coordinates: string[] };
export function InvestigationPanel({ token }: { token: string }) {
  const [query, setQuery] = useState(""); const [rows, setRows] = useState<Detection[]>([]);
  const [path, setPath] = useState<PathResult | null>(null); const [error, setError] = useState("");
  useEffect(() => { apiRequest<Detection[]>("/detections", token).then(setRows).catch(e => setError(e.message)); }, [token]);
  async function search() {
    setError(""); setPath(null);
    try {
      const results = await apiRequest<Detection[]>(`/detections?plate=${encodeURIComponent(query)}`, token);
      setRows(results);
      if (results.length) setPath(await apiRequest<PathResult>(`/investigations/path?plate=${encodeURIComponent(query)}`, token));
    } catch (e) { setError(e instanceof Error ? e.message : "Search unavailable"); }
  }
  return <section className="surakshPanel runtimePanel"><h2>Vehicle Search</h2>
    <form className="toolbar" onSubmit={e => { e.preventDefault(); void search(); }}><input aria-label="Registration search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Registration number" required /><button className="primaryButton">Search</button></form>
    {error && <p className="errorBanner">{error}</p>}
    <p>{rows.length} persisted detections · DEMO / SYNTHETIC INPUT</p>
    {path && <><h2>Observed Camera Detection Path</h2><p>Camera observations in chronological order; connecting lines do not identify roads travelled. Coordinates are synthetic demo locations.</p><PathMap points={path.points} />
      {path.missing_coordinates.length > 0 && <p>{path.missing_coordinates.length} observations have no coordinates and cannot be plotted.</p>}</>}
    <div className="tableWrap"><table><thead><tr><th>Plate / ID</th><th>Camera / Department</th><th>VMS / Timestamp</th><th>YOLO / OCR</th></tr></thead><tbody>{rows.map(r => <tr key={r.id}><td><strong>{r.plate_text ?? "Not read"}</strong><small>{r.id}</small></td><td>{r.camera_name}<small>{r.department_name}</small></td><td>{r.source_system}<small>{timestamp(r.detected_at)}</small></td><td>{(r.vehicle_confidence * 100).toFixed(1)}% / {((r.plate_confidence ?? 0) * 100).toFixed(1)}%</td></tr>)}</tbody></table></div>
  </section>;
}

type AuditRow = { id: string; created_at: string; user_id: string | null; action: string; resource_type: string; resource_id: string; new_values: Record<string, unknown> };
export function AuditPanel({ token }: { token: string }) {
  const [rows, setRows] = useState<AuditRow[]>([]); const [error, setError] = useState(""); const [filter, setFilter] = useState("");
  useEffect(() => { apiRequest<AuditRow[]>("/audit", token).then(setRows).catch(e => setError(e.message)); }, [token]);
  return <section className="surakshPanel runtimePanel"><h2>Audit Logs</h2><input aria-label="Filter audit actions" placeholder="Filter action or resource" value={filter} onChange={e => setFilter(e.target.value)} />{error && <p className="errorBanner">{error}</p>}
    <div className="tableWrap"><table><thead><tr><th>Time / Actor</th><th>Action</th><th>Resource / Department</th><th>Result</th></tr></thead><tbody>{rows.filter(r => `${r.action} ${r.resource_id}`.includes(filter)).map(r => <tr key={r.id}><td>{timestamp(r.created_at)}<small>{r.user_id ?? "Authenticated machine / system"}</small></td><td>{r.action}</td><td>{r.resource_type}: {r.resource_id}<small>{String(r.new_values.department_id ?? "")}</small></td><td>{String(r.new_values.result ?? "Recorded")}</td></tr>)}</tbody></table></div>
  </section>;
}

export function WatchlistPanel({ token, items, departments, refresh }: { token: string; items: Watchlist[]; departments: Department[]; refresh: () => void }) {
  const [name, setName] = useState(""); const [plate, setPlate] = useState(""); const [department, setDepartment] = useState(""); const [error, setError] = useState("");
  async function create() {
    try { const list = await apiRequest<Watchlist>("/watchlists", token, { method: "POST", body: JSON.stringify({ name, department_id: department || departments[0]?.id, description: "DEMO / SYNTHETIC INPUT", active: true }) });
      await apiRequest(`/watchlists/${list.id}/entries`, token, { method: "POST", body: JSON.stringify({ plate_text: plate, priority: "HIGH", reason: "Synthetic hackathon vehicle-of-interest demonstration" }) }); refresh(); setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "Watchlist operation failed"); }
  }
  return <section className="surakshPanel runtimePanel"><h2>Watchlists</h2><form className="toolbar" onSubmit={e => { e.preventDefault(); void create(); }}>
    <input placeholder="Watchlist name" aria-label="Watchlist name" value={name} onChange={e => setName(e.target.value)} required /><input placeholder="Plate" aria-label="Watchlist plate" value={plate} onChange={e => setPlate(e.target.value)} required />
    <select aria-label="Department" value={department} onChange={e => setDepartment(e.target.value)}><option value="">Select department</option>{departments.map(d => <option value={d.id} key={d.id}>{d.name}</option>)}</select><button className="primaryButton">Create watchlist</button></form>
    {error && <p className="errorBanner">{error}</p>}{items.map(w => <article className="runtimeAlert" key={w.id}><h3>{w.name}</h3><p>{w.description} · {w.active ? "ACTIVE" : "INACTIVE"}</p><small>{w.id}</small>{w.entries.map(e => <p key={e.id}><strong>{e.plate_text} · {e.priority.toUpperCase()}</strong> · {e.reason}</p>)}</article>)}
  </section>;
}

export function IntegrationPanel({ token, systems, refresh }: { token: string; systems: VMSSystem[]; refresh: () => void }) {
  const [message, setMessage] = useState("");
  async function sync(id: string) { try { await apiRequest(`/integrations/vms/${id}/sync`, token, { method: "POST" }); setMessage("Connector sync completed"); refresh(); } catch(e) { setMessage(e instanceof Error ? e.message : "Sync failed"); } }
  return <section className="surakshPanel runtimePanel"><h2>VMS Integrations</h2><p>DEMO / SYNTHETIC configuration · Departmental VMS ownership is preserved.</p><p role="status">{message}</p>{systems.map(v => <article className="runtimeAlert" key={v.id}><h3>{v.name}</h3><p>{v.vendor} · {v.camera_count} cameras · {v.status}</p><p>{v.base_url}</p><p>Last sync: {v.last_sync ? timestamp(v.last_sync) : "Never"}</p><button className="secondaryButton" onClick={() => void sync(v.id)}>Sync {v.name}</button></article>)}</section>;
}
