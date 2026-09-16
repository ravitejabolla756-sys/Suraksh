from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None
    whatsapp_phone: str | None
    role: str
    created_at: datetime


class StaffInviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    whatsapp_phone: str | None = Field(default=None, max_length=20)
    role: str = Field(default="operator")
    temporary_password: str = Field(default="Suraksh123!", min_length=8, max_length=100)


class CameraCreate(BaseModel):
    name: str
    source_url: str = "demo://camera"
    location_name: str = "Campus"


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_url: str
    location_name: str
    status: str
    last_heartbeat: datetime
    resolution_width: int
    resolution_height: int
    fps: int
    department_id: str | None = None
    external_id: str | None = None
    district: str
    zone: str
    latitude: float | None = None
    longitude: float | None = None
    camera_type: str
    vendor: str
    model: str
    vms_system_id: str | None = None
    protocol: str
    stream_status: str
    storage_type: str
    retention_days: int
    health_status: str
    is_demo: bool


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    camera_id: str
    name: str
    zone_type: str
    polygon: dict
    crowd_threshold: int | None = None


class EventIngest(BaseModel):
    org_id: str
    camera_id: str
    edge_server_id: str | None = None
    zone_id: str | None = None
    type: str
    confidence: float = Field(ge=0, le=1)
    edge_detected_at: datetime | None = None
    snapshot_url: str | None = None
    video_clip_url: str | None = None
    metadata: dict = Field(default_factory=dict)


class EventOut(BaseModel):
    id: str
    org_id: str
    camera_id: str
    edge_server_id: str | None
    zone_id: str | None
    type: str
    confidence: float
    edge_detected_at: datetime
    cloud_received_at: datetime
    snapshot_url: str | None
    video_clip_url: str | None
    metadata: dict
    alert_sent: bool
    dismissed_by: str | None
    dismissed_at: datetime | None
    dismiss_reason: str | None
    camera_name: str | None = None
    zone_name: str | None = None


class SafetyEvidenceReferenceIn(BaseModel):
    camera_id: str
    sequence: int = Field(ge=0)
    timestamp: datetime
    recording_id: str | None = None
    frame_uri: str | None = None
    offset_seconds: float | None = None
    sha256: str | None = None


class SafetyTemporalWindowIn(BaseModel):
    started_at: datetime
    ended_at: datetime


class SafetyIncidentIngest(BaseModel):
    org_id: str
    camera_id: str
    event_type: str
    confidence: float = Field(ge=0, le=1)
    timestamp: datetime
    model_versions: dict[str, str] = Field(min_length=1)
    contributing_signals: dict[str, float] = Field(default_factory=dict)
    evidence_references: list[SafetyEvidenceReferenceIn] = Field(default_factory=list)
    temporal_window: SafetyTemporalWindowIn
    uncertainty: float = Field(default=0, ge=0, le=1)
    tracks: list[int] = Field(default_factory=list)
    zone_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class DismissRequest(BaseModel):
    reason: str = "handled"


class AlertRuleCreate(BaseModel):
    name: str
    event_type: str
    confidence_threshold: float = Field(default=0.7, ge=0, le=1)
    camera_id: str | None = None
    zone_id: str | None = None
    condition_type: str | None = None
    condition_value: int | None = None
    enabled: bool = True
    notify_channels: list[str] = Field(default_factory=lambda: ["whatsapp"])
    notify_user_ids: list[str] = Field(default_factory=list)
    suppress_duration_sec: int = 60


class AlertRuleOut(AlertRuleCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    created_at: datetime


class AnalyticsSummary(BaseModel):
    cameras_online: int
    cameras_total: int
    events_today: int
    active_alerts: int
    event_breakdown: dict[str, int]
    recent_camera_health: list[dict]
    people_visible: int = 0
    vehicles_visible: int = 0
    cars: int = 0
    motorcycles: int = 0
    buses: int = 0
    trucks: int = 0
    unique_people: int = 0
    unique_vehicles: int = 0


class AnalyticsIngest(BaseModel):
    camera_id: str
    department_id: str
    source_vms: str = Field(min_length=1, max_length=100)
    bucket_start: datetime
    bucket_end: datetime
    people_visible_peak: int = Field(default=0, ge=0)
    vehicle_visible_peak: int = Field(default=0, ge=0)
    unique_people: int = Field(default=0, ge=0)
    unique_vehicles: int = Field(default=0, ge=0)
    unique_cars: int = Field(default=0, ge=0)
    unique_motorcycles: int = Field(default=0, ge=0)
    unique_buses: int = Field(default=0, ge=0)
    unique_trucks: int = Field(default=0, ge=0)
    cars_crossed_a_to_b: int = Field(default=0, ge=0)
    cars_crossed_b_to_a: int = Field(default=0, ge=0)
    motorcycles_crossed_a_to_b: int = Field(default=0, ge=0)
    motorcycles_crossed_b_to_a: int = Field(default=0, ge=0)
    buses_crossed_a_to_b: int = Field(default=0, ge=0)
    buses_crossed_b_to_a: int = Field(default=0, ge=0)
    trucks_crossed_a_to_b: int = Field(default=0, ge=0)
    trucks_crossed_b_to_a: int = Field(default=0, ge=0)


class AnalyticsSnapshotOut(AnalyticsIngest):
    id: str
    created_at: datetime


class NotificationLogOut(BaseModel):
    id: str
    org_id: str
    event_id: str
    alert_rule_id: str | None
    user_id: str | None
    channel: str
    recipient: str
    status: str
    provider: str
    message: str
    created_at: datetime
    event_type: str | None = None
    camera_name: str | None = None


class PilotLeadCreate(BaseModel):
    school_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)
    city: str = Field(min_length=2, max_length=100)
    camera_count: str = Field(default="8", max_length=20)
    source: str = Field(default="website", max_length=100)


class PilotLeadOut(PilotLeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    notes: str
    created_at: datetime


class PilotLeadUpdate(BaseModel):
    status: str = Field(min_length=2, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    district: str
    is_demo: bool


class CameraPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    department_id: str | None = None
    district: str | None = Field(default=None, max_length=100)
    zone: str | None = Field(default=None, max_length=100)
    latitude: float | None = Field(default=None, ge=6, le=38)
    longitude: float | None = Field(default=None, ge=68, le=98)
    vendor: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    camera_type: str | None = Field(default=None, max_length=50)
    protocol: str | None = Field(default=None, max_length=50)
    stream_endpoint: str | None = Field(default=None, max_length=500)
    health_status: str | None = None
    is_demo: bool | None = None


class CameraRegistryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = Field(default=None, max_length=100)
    department_id: str
    district: str = Field(min_length=2, max_length=100)
    zone: str = Field(default="Unknown", max_length=100)
    latitude: float | None = Field(default=None, ge=6, le=38)
    longitude: float | None = Field(default=None, ge=68, le=98)
    camera_type: str = Field(default="fixed", max_length=50)
    vendor: str = Field(default="Unknown", max_length=100)
    model: str = Field(default="Unknown", max_length=100)
    vms_system_id: str | None = None
    protocol: str = Field(default="RTSP", max_length=50)
    stream_endpoint: str = Field(default="", max_length=500)
    storage_type: str = Field(default="VMS", max_length=50)
    retention_days: int = Field(default=30, ge=0, le=3650)
    is_demo: bool = True


class CameraImportResult(BaseModel):
    created_count: int
    updated_count: int
    failed_count: int
    errors: list[dict]


class VMSOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    department_id: str
    name: str
    vendor: str
    base_url: str
    status: str
    last_sync: datetime | None
    is_demo: bool
    camera_count: int = 0


class DetectionCreate(BaseModel):
    request_id: str | None = Field(default=None, min_length=8, max_length=128)
    camera_id: str
    department_id: str
    source_system: str
    detected_at: datetime
    vehicle_class: str = Field(min_length=1, max_length=50)
    vehicle_confidence: float = Field(ge=0, le=1)
    plate_text: str | None = Field(default=None, max_length=32)
    plate_confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict = Field(default_factory=dict)
    is_demo: bool = True


class DetectionOut(DetectionCreate):
    id: str
    camera_name: str | None = None
    district: str | None = None
    department_name: str | None = None


class WatchlistCreate(BaseModel):
    department_id: str
    name: str = Field(min_length=2, max_length=255)
    description: str = Field(default="", max_length=1000)
    active: bool = True


class WatchlistEntryCreate(BaseModel):
    plate_text: str = Field(min_length=4, max_length=32)
    priority: str = Field(default="medium", max_length=30)
    reason: str = Field(default="", max_length=500)
    active: bool = True


class WatchlistEntryOut(WatchlistEntryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    watchlist_id: str


class WatchlistOut(WatchlistCreate):
    id: str
    created_by: str
    entries: list[WatchlistEntryOut] = Field(default_factory=list)


class GapAnalysis(BaseModel):
    total_cameras: int
    by_district: dict[str, int]
    online_ratio: float
    offline_ratio: float
    degraded_ratio: float
    low_coverage_districts: list[str]
    synthetic_data_notice: str
