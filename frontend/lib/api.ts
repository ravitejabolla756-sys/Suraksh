export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type User = {
  id: string;
  org_id: string;
  email: string;
  name: string;
  role: "admin" | "operator" | "viewer";
};

export type StaffUser = {
  id: string;
  org_id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string | null;
  whatsapp_phone: string | null;
  role: "admin" | "operator" | "viewer";
  created_at: string;
};

export type StaffInviteCreate = {
  email: string;
  first_name: string;
  last_name: string;
  phone: string | null;
  whatsapp_phone: string | null;
  role: "admin" | "operator" | "viewer";
  temporary_password: string;
};

export type Camera = {
  id: string;
  name: string;
  source_url: string;
  location_name: string;
  status: "online" | "offline" | "error" | "degraded";
  last_heartbeat: string;
  resolution_width: number;
  resolution_height: number;
  fps: number;
  department_id: string | null;
  external_id: string | null;
  district: string;
  zone: string;
  latitude: number | null;
  longitude: number | null;
  camera_type: string;
  vendor: string;
  model: string;
  vms_system_id: string | null;
  protocol: string;
  stream_status: string;
  storage_type: string;
  retention_days: number;
  health_status: string;
  is_demo: boolean;
};

export type CameraCreate = {
  name: string;
  source_url: string;
  location_name: string;
};

export type EventItem = {
  id: string;
  org_id: string;
  camera_id: string;
  edge_server_id: string | null;
  zone_id: string | null;
  type: string;
  confidence: number;
  edge_detected_at: string;
  cloud_received_at: string;
  snapshot_url: string | null;
  video_clip_url: string | null;
  metadata: Record<string, unknown>;
  alert_sent: boolean;
  dismissed_by: string | null;
  dismissed_at: string | null;
  dismiss_reason: string | null;
  camera_name: string | null;
  zone_name: string | null;
};

export type AlertRule = {
  id: string;
  org_id: string;
  name: string;
  event_type: string;
  confidence_threshold: number;
  camera_id: string | null;
  zone_id: string | null;
  condition_type: string | null;
  condition_value: number | null;
  enabled: boolean;
  notify_channels: string[];
  notify_user_ids: string[];
  suppress_duration_sec: number;
  created_at: string;
};

export type AlertRuleCreate = {
  name: string;
  event_type: string;
  confidence_threshold: number;
  camera_id: string | null;
  zone_id: string | null;
  condition_type: string | null;
  condition_value: number | null;
  enabled: boolean;
  notify_channels: string[];
  notify_user_ids: string[];
  suppress_duration_sec: number;
};

export type AnalyticsSummary = {
  cameras_online: number;
  cameras_total: number;
  events_today: number;
  active_alerts: number;
  event_breakdown: Record<string, number>;
  recent_camera_health: Array<{ id: string; name: string; status: string; last_heartbeat: string }>;
  people_visible: number; vehicles_visible: number; cars: number; motorcycles: number; buses: number; trucks: number;
  unique_people: number; unique_vehicles: number;
};

export type AnalyticsBucket = {
  id: string; camera_id: string; department_id: string; source_vms: string; bucket_start: string; bucket_end: string;
  people_visible_peak: number; vehicle_visible_peak: number; unique_people: number; unique_vehicles: number;
  unique_cars: number; unique_motorcycles: number; unique_buses: number; unique_trucks: number;
  cars_crossed_a_to_b: number; cars_crossed_b_to_a: number; motorcycles_crossed_a_to_b: number; motorcycles_crossed_b_to_a: number;
  buses_crossed_a_to_b: number; buses_crossed_b_to_a: number; trucks_crossed_a_to_b: number; trucks_crossed_b_to_a: number; created_at: string;
};

export type CameraAnalytics = {
  camera_id: string; camera_name: string; source_vms: string | null; traffic_state: string;
  current: { people: number; vehicles: number }; period_totals: Record<string, number>;
  line_crossings: Record<string, number>; timeseries: AnalyticsBucket[];
};

export type PilotLead = {
  id: string;
  school_name: string;
  email: string;
  phone: string;
  city: string;
  camera_count: string;
  source: string;
  status: string;
  notes: string;
  created_at: string;
};

export type NotificationLog = {
  id: string;
  org_id: string;
  event_id: string;
  alert_rule_id: string | null;
  user_id: string | null;
  channel: string;
  recipient: string;
  status: string;
  provider: string;
  message: string;
  created_at: string;
  event_type: string | null;
  camera_name: string | null;
};

export type Department = { id: string; name: string; code: string; district: string; is_demo: boolean };
export type VMSSystem = { id: string; department_id: string; name: string; vendor: string; base_url: string; status: string; last_sync: string | null; is_demo: boolean; camera_count: number };
export type Detection = {
  id: string; camera_id: string; department_id: string; source_system: string; detected_at: string;
  vehicle_class: string; vehicle_confidence: number; plate_text: string | null; plate_confidence: number | null;
  evidence_url: string | null; latitude: number | null; longitude: number | null; metadata: Record<string, unknown>;
  is_demo: boolean; camera_name: string | null; district: string | null; department_name: string | null;
};
export type WatchlistEntry = { id: string; watchlist_id: string; plate_text: string; priority: string; reason: string; active: boolean };
export type Watchlist = { id: string; department_id: string; name: string; description: string; active: boolean; created_by: string; entries: WatchlistEntry[] };
export type GapAnalysis = { total_cameras: number; by_district: Record<string, number>; online_ratio: number; offline_ratio: number; degraded_ratio: number; low_coverage_districts: string[]; synthetic_data_notice: string };

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiRequest<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers
    }
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(typeof body.detail === "string" ? body.detail : "Request failed", response.status);
  }
  return response.json() as Promise<T>;
}
