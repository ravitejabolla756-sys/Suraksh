"use client";
import { useEffect, useMemo, useRef } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Detection } from "@/lib/api";

export default function ObservedPathMap({ points }: { points: Detection[] }) {
  const ordered = useMemo(() => [...points].filter(p => p.latitude !== null && p.longitude !== null).sort((a,b) => a.detected_at.localeCompare(b.detected_at)), [points]);
  const positions = useMemo<[number, number][]>(() => ordered.map(p => [p.latitude!, p.longitude!]), [ordered]);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;
    const map = L.map(container, { center: [23.0225, 72.5714], zoom: 13 });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap contributors" }).addTo(map);
    mapRef.current = map;
    layerRef.current = L.layerGroup().addTo(map);
    return () => {
      layerRef.current?.clearLayers();
      layerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    if (positions.length >= 2) L.polyline(positions, { color: "#42d392", weight: 4 }).addTo(layer);
    ordered.forEach((point, index) => {
      L.circleMarker(positions[index], { radius: 9, color: "#f2b84b", fillOpacity: 1 })
        .bindPopup(`${index + 1}. ${escapeHtml(point.camera_name ?? "Camera")}<br />${escapeHtml(point.plate_text ?? "Plate not read")} · ${escapeHtml(point.source_system)}<br />${escapeHtml(point.detected_at)}`)
        .addTo(layer);
    });
    if (positions.length) map.fitBounds(L.latLngBounds(positions), { padding: [45, 45], maxZoom: 15 });
  }, [ordered, positions]);

  return <div data-path-points={positions.length} ref={containerRef} className="observedMap" aria-label="Observed camera detection path map" />;
}

function escapeHtml(value: string) {
  return value.replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character] ?? character);
}
