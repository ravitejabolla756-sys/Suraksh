"use client";
import { useState } from "react";
import { API_URL, Camera, Department, VMSSystem } from "@/lib/api";

export function RegistryPanel({ token, cameras, departments, systems, onCamera }: {
  token: string; cameras: Camera[]; departments: Department[]; systems: VMSSystem[]; onCamera: (c: Camera) => void;
}) {
  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState("");
  const [error, setError] = useState("");
  const filtered = cameras.filter(c => (!department || c.department_id === department) && `${c.name} ${c.external_id} ${c.district} ${c.vendor}`.toLowerCase().includes(query.toLowerCase()));
  async function downloadTemplate() {
    try {
      const response = await fetch(`${API_URL}/cameras/import/template`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error(`CSV template HTTP ${response.status}`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = "suraksh-cameras.csv"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "Template unavailable"); }
  }
  return <section className="surakshPanel runtimePanel"><h2>Centralised CCTV Registry</h2><p>{filtered.length} / {cameras.length} records · DEMO / SYNTHETIC</p>
    <div className="toolbar"><input aria-label="Search cameras" placeholder="Camera, ID, district, vendor" value={query} onChange={e => setQuery(e.target.value)} />
      <select aria-label="Filter department" value={department} onChange={e => setDepartment(e.target.value)}><option value="">All departments</option>{departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
      <button className="secondaryButton" onClick={() => void downloadTemplate()}>Download CSV template</button></div>
    {error && <p className="errorBanner">{error}</p>}
    <div className="tableWrap"><table><thead><tr><th>Camera</th><th>Department</th><th>District / zone</th><th>Vendor / VMS</th><th>Source / Health</th><th>Details</th></tr></thead><tbody>
      {filtered.map(c => <tr key={c.id}><td><strong>{c.external_id}</strong><small>{c.name}</small></td><td>{departments.find(d => d.id === c.department_id)?.name ?? "Unassigned"}</td><td>{c.district}<small>{c.zone}</small></td><td>{c.vendor}<small>{systems.find(v => v.id === c.vms_system_id)?.name ?? "Unassigned"}</small></td><td>{c.protocol}<small>{c.health_status}</small></td><td><button className="rowButton" onClick={() => onCamera(c)}>Details</button></td></tr>)}
    </tbody></table></div>{!filtered.length && <p>No matching cameras.</p>}
  </section>;
}
