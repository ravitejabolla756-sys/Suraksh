"use client";

import { useEffect, useRef } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Camera } from "@/lib/api";

export function GisMap({ cameras, onSelect }: { cameras: Camera[]; onSelect: (camera: Camera) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container, { center: [22.3, 71.7], zoom: 7, scrollWheelZoom: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap contributors" }).addTo(map);
    mapRef.current = map;
    markersRef.current = L.layerGroup().addTo(map);

    return () => {
      markersRef.current?.clearLayers();
      markersRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const layer = markersRef.current;
    const map = mapRef.current;
    if (!layer || !map) return;
    layer.clearLayers();
    const located = cameras.filter((camera) => camera.latitude !== null && camera.longitude !== null);
    located.forEach((camera) => {
      const color = camera.health_status === "ONLINE" ? "#42d392" : camera.health_status === "DEGRADED" ? "#f2b84b" : "#e66b6b";
      L.circleMarker([camera.latitude as number, camera.longitude as number], { radius: 8, color, fillOpacity: 0.9 })
        .bindPopup(`<strong>${escapeHtml(camera.name)}</strong><br />${escapeHtml(camera.district)} · ${escapeHtml(camera.health_status)}`)
        .on("click", () => onSelect(camera))
        .addTo(layer);
    });
    if (located.length > 1) map.fitBounds(L.latLngBounds(located.map((camera) => [camera.latitude as number, camera.longitude as number])), { padding: [24, 24], maxZoom: 10 });
    else if (located.length === 1) map.setView([located[0].latitude as number, located[0].longitude as number], 10);
  }, [cameras, onSelect]);

  return <div ref={containerRef} className="gisMap" aria-label="Gujarat camera registry map" />;
}

function escapeHtml(value: string) {
  return value.replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character] ?? character);
}
