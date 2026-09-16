import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base
from app.core.config import get_settings

try:
    from geoalchemy2 import Geography
except ImportError:  # pragma: no cover - local lightweight test fallback
    Geography = None

LOCATION_TYPE = (
    Geography(geometry_type="POINT", srid=4326, spatial_index=True)
    if Geography and get_settings().postgis_enabled
    else String(128)
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"


class CameraStatus(str, enum.Enum):
    online = "online"
    offline = "offline"
    error = "error"
    degraded = "degraded"


class EventType(str, enum.Enum):
    person = "person"
    fight = "fight"
    fire = "fire"
    smoke = "smoke"
    fall = "fall"
    intrusion = "intrusion"
    crowd = "crowd"
    loitering = "loitering"
    camera_offline = "camera_offline"
    vehicle_collision = "vehicle_collision"
    vehicle_crash = "vehicle_crash"
    pedestrian_vehicle_collision = "pedestrian_vehicle_collision"
    person_fall = "person_fall"


class HealthStatus(str, enum.Enum):
    online = "ONLINE"
    offline = "OFFLINE"
    degraded = "DEGRADED"
    unknown = "UNKNOWN"


class ConnectorStatus(str, enum.Enum):
    connected = "CONNECTED"
    degraded = "DEGRADED"
    offline = "OFFLINE"
    unknown = "UNKNOWN"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str] = mapped_column(String(100), default="Hyderabad")
    plan: Mapped[str] = mapped_column(String(50), default="professional")
    camera_limit: Mapped[int] = mapped_column(Integer, default=8)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    users: Mapped[list["User"]] = relationship(back_populates="org")
    cameras: Mapped[list["Camera"]] = relationship(back_populates="org")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class VMSSystem(Base):
    __tablename__ = "vms_systems"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ConnectorStatus] = mapped_column(Enum(ConnectorStatus), default=ConnectorStatus.unknown)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vms_system_id: Mapped[str] = mapped_column(ForeignKey("vms_systems.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    credential_hash: Mapped[str | None] = mapped_column(String(128))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ConnectorStatus] = mapped_column(Enum(ConnectorStatus), default=ConnectorStatus.unknown)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PilotLead(Base):
    __tablename__ = "pilot_leads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    school_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    camera_count: Mapped[str] = mapped_column(String(20), default="8")
    status: Mapped[str] = mapped_column(String(50), default="new")
    source: Mapped[str] = mapped_column(String(100), default="website")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str | None] = mapped_column(String(20))
    whatsapp_phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, default=Role.admin)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    org: Mapped[Organization] = relationship(back_populates="users")


class EdgeServer(Base):
    __tablename__ = "edge_servers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="online")
    version: Mapped[str] = mapped_column(String(50), default="0.1.0")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(100), index=True)
    district: Mapped[str] = mapped_column(String(100), default="Unknown", index=True)
    zone: Mapped[str] = mapped_column(String(100), default="Unknown", index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location: Mapped[str | None] = mapped_column(LOCATION_TYPE)
    camera_type: Mapped[str] = mapped_column(String(50), default="fixed")
    vendor: Mapped[str] = mapped_column(String(100), default="Unknown", index=True)
    model: Mapped[str] = mapped_column(String(100), default="Unknown")
    vms_system_id: Mapped[str | None] = mapped_column(ForeignKey("vms_systems.id"), index=True)
    protocol: Mapped[str] = mapped_column(String(50), default="RTSP")
    stream_status: Mapped[str] = mapped_column(String(50), default="UNKNOWN")
    storage_type: Mapped[str] = mapped_column(String(50), default="VMS")
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    installation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[HealthStatus] = mapped_column(Enum(HealthStatus), default=HealthStatus.unknown, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    edge_server_id: Mapped[str | None] = mapped_column(ForeignKey("edge_servers.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), default="demo://camera")
    location_name: Mapped[str] = mapped_column(String(255), default="Campus")
    status: Mapped[CameraStatus] = mapped_column(Enum(CameraStatus), default=CameraStatus.online)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    resolution_width: Mapped[int] = mapped_column(Integer, default=1280)
    resolution_height: Mapped[int] = mapped_column(Integer, default=720)
    fps: Mapped[int] = mapped_column(Integer, default=15)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    org: Mapped[Organization] = relationship(back_populates="cameras")
    zones: Mapped[list["Zone"]] = relationship(back_populates="camera")


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(50), default="restricted")
    polygon: Mapped[dict] = mapped_column(JSON, default=dict)
    crowd_threshold: Mapped[int | None] = mapped_column(Integer)
    loiter_timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    intrusion_alert_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    camera: Mapped[Camera] = relationship(back_populates="zones")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    edge_server_id: Mapped[str | None] = mapped_column(ForeignKey("edge_servers.id"))
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id"))
    type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    edge_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    cloud_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    snapshot_url: Mapped[str | None] = mapped_column(String(500))
    video_clip_url: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismiss_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class SafetyIncidentGroup(Base):
    """Durable deduplication pointer for one continuous safety episode.

    This is integration state, not a replacement incident aggregate. The
    existing Event row remains the incident record and owns its lifecycle,
    evidence, and notifications.
    """

    __tablename__ = "safety_incident_groups"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    incident_event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    group_key: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("org_id", "camera_id", "group_key", name="uq_safety_group_scope"),
    )


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.7)
    camera_id: Mapped[str | None] = mapped_column(ForeignKey("cameras.id"))
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id"))
    condition_type: Mapped[str | None] = mapped_column(String(50))
    condition_value: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_channels: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["whatsapp"])
    notify_user_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    suppress_duration_sec: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False)
    alert_rule_id: Mapped[str | None] = mapped_column(ForeignKey("alert_rules.id"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="queued")
    provider: Mapped[str] = mapped_column(String(50), default="demo")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), default="")
    resource_id: Mapped[str] = mapped_column(String(255), default="")
    new_values: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CameraHealth(Base):
    __tablename__ = "camera_health"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, unique=True)
    health_status: Mapped[HealthStatus] = mapped_column(Enum(HealthStatus), default=HealthStatus.unknown)
    stream_reachable: Mapped[bool] = mapped_column(Boolean, default=False)
    last_frame_received: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    measured_fps: Mapped[float | None] = mapped_column(Float)
    codec: Mapped[str | None] = mapped_column(String(50))
    resolution: Mapped[str | None] = mapped_column(String(50))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DetectionEvent(Base):
    __tablename__ = "detection_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    vehicle_class: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    plate_text: Mapped[str | None] = mapped_column(String(32), index=True)
    plate_confidence: Mapped[float | None] = mapped_column(Float)
    evidence_url: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CameraAnalyticsSnapshot(Base):
    """One persisted time bucket per camera, never one row per video frame."""
    __tablename__ = "camera_analytics_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), nullable=False, index=True)
    source_vms: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    people_visible_peak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vehicle_visible_peak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_people: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_vehicles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_cars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_motorcycles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_buses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_trucks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cars_crossed_a_to_b: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cars_crossed_b_to_a: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    motorcycles_crossed_a_to_b: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    motorcycles_crossed_b_to_a: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    buses_crossed_a_to_b: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    buses_crossed_b_to_a: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trucks_crossed_a_to_b: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trucks_crossed_b_to_a: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    watchlist_id: Mapped[str] = mapped_column(ForeignKey("watchlists.id"), nullable=False, index=True)
    plate_text: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(30), default="medium")
    reason: Mapped[str] = mapped_column(String(500), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), nullable=False, index=True)
    detection_id: Mapped[str] = mapped_column(ForeignKey("detection_events.id"), nullable=False, index=True)
    watchlist_entry_id: Mapped[str] = mapped_column(ForeignKey("watchlist_entries.id"), nullable=False)
    priority: Mapped[str] = mapped_column(String(30), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
