from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.config import get_settings
from app.models.entities import (
    AlertRule,
    Camera,
    ConnectorStatus,
    Department,
    DetectionEvent,
    EdgeServer,
    Event,
    EventType,
    NotificationLog,
    Organization,
    User,
    VMSSystem,
    Watchlist,
    WatchlistEntry,
    HealthStatus,
    Zone,
)


def _ensure_local_op_camera(db: Session, org_id: str) -> None:
    """Keep the user-provided OP.mp4 source registered across local restarts."""
    settings = get_settings()
    if not settings.demo_runtime_only:
        return
    department = db.query(Department).filter(
        Department.org_id == org_id,
        Department.code == "MUNICIPAL-DEMO",
    ).first()
    if not department:
        return

    values = {
        "name": "AHM-DEMO-03 - OP.mp4 / LOCAL AI SOURCE",
        "source_url": "http://127.0.0.1:8000/demo-media/OP.mp4",
        "protocol": "MP4",
        "stream_status": "RECORDED FILE READABLE",
        "health_status": HealthStatus.online,
        "status": "online",
        "is_demo": True,
        "resolution_width": 1918,
        "resolution_height": 1138,
        "fps": 30,
    }
    camera = db.query(Camera).filter(
        Camera.org_id == org_id,
        Camera.external_id == "OP-DEMO-01",
    ).first()
    if camera:
        for key, value in values.items():
            setattr(camera, key, value)
        return

    db.add(Camera(
        id="cam_op_demo",
        org_id=org_id,
        department_id=department.id,
        external_id="OP-DEMO-01",
        district="Local Demo",
        zone="User-provided OP.mp4",
        camera_type="fixed",
        vendor="Local video source",
        model="OP.mp4 · 1918x1138 @ 30 FPS",
        protocol=values["protocol"],
        stream_status=values["stream_status"],
        health_status=values["health_status"],
        is_demo=True,
        name=values["name"],
        source_url=values["source_url"],
        location_name="Local video source",
        status=values["status"],
        resolution_width=values["resolution_width"],
        resolution_height=values["resolution_height"],
        fps=values["fps"],
    ))


def seed_demo(db: Session) -> None:
    existing_org = db.query(Organization).first()
    if existing_org:
        _ensure_local_op_camera(db, existing_org.id)
        db.commit()
        return

    org = Organization(
        id="org_demo_school",
        name="Gujarat Multi-Agency Control Room - DEMO",
        email="controlroom@suraksh.demo",
        phone="+919876543210",
        city="Hyderabad",
        plan="professional",
        camera_limit=8,
    )
    db.add(org)

    admin = User(
        id="usr_principal",
        org_id=org.id,
        email="admin@suraksh.demo",
        password_hash=hash_password("Suraksh123!"),
        first_name="State",
        last_name="Administrator",
        phone="+918674938201",
        whatsapp_phone="+918674938201",
        role="admin",
    )
    operator = User(
        id="usr_security",
        org_id=org.id,
        email="operator@suraksh.demo",
        password_hash=hash_password("Suraksh123!"),
        first_name="Control Room",
        last_name="Operator",
        phone="+919123456789",
        whatsapp_phone="+919123456789",
        role="operator",
    )
    db.add_all([admin, operator])

    edge = EdgeServer(
        id="edge_demo_01",
        org_id=org.id,
        name="Gujarat Edge Node - DEMO",
        status="online",
        config={"max_streams": 4, "mode": "demo"},
    )
    db.add(edge)

    departments = [
        Department(id="dept_home_demo", org_id=org.id, name="Home Department - DEMO", code="HOME-DEMO", district="Ahmedabad", is_demo=True),
        Department(id="dept_transport_demo", org_id=org.id, name="Transport Department - DEMO", code="TRANSPORT-DEMO", district="Surat", is_demo=True),
        Department(id="dept_municipal_demo", org_id=org.id, name="Municipal Corporation - DEMO", code="MUNICIPAL-DEMO", district="Vadodara", is_demo=True),
    ]
    db.add_all(departments)
    vms_a = VMSSystem(id="vms_a_demo", department_id="dept_home_demo", name="Department VMS A - DEMO", vendor="Federated Vendor A", base_url="http://vms-a:8091", status=ConnectorStatus.connected, is_demo=True)
    vms_b = VMSSystem(id="vms_b_demo", department_id="dept_transport_demo", name="Department VMS B - DEMO", vendor="Federated Vendor B", base_url="http://vms-b:8092", status=ConnectorStatus.connected, is_demo=True)
    db.add_all([vms_a, vms_b])

    cameras = [
        Camera(
            id="cam_gate_1",
            org_id=org.id,
            edge_server_id=edge.id,
            name="Gate 1",
            source_url="rtsp://mediamtx:8554/vms-a",
            location_name="Main Entrance",
            status="online",
            department_id="dept_home_demo",
            external_id="CAM_A_01",
            district="Ahmedabad",
            zone="Relief Road",
            latitude=23.0225,
            longitude=72.5714,
            camera_type="fixed",
            vendor="Federated Vendor A",
            model="VMS-A-Edge",
            vms_system_id=vms_a.id,
            protocol="RTSP",
            stream_status="ONLINE",
            health_status=HealthStatus.online,
            is_demo=True,
        ),
        Camera(
            id="cam_hallway",
            org_id=org.id,
            edge_server_id=edge.id,
            name="Main Hallway",
            source_url="rtsp://mediamtx:8554/vms-b",
            location_name="Academic Block",
            status="online",
            department_id="dept_transport_demo",
            external_id="B-100",
            district="Surat",
            zone="Ring Road",
            latitude=21.1702,
            longitude=72.8311,
            camera_type="ptz",
            vendor="Federated Vendor B",
            model="VMS-B-PTZ",
            vms_system_id=vms_b.id,
            protocol="HLS",
            stream_status="ONLINE",
            health_status=HealthStatus.online,
            is_demo=True,
        ),
        Camera(
            id="cam_lab_2",
            org_id=org.id,
            edge_server_id=edge.id,
            name="Lab 2",
            source_url="demo://lab-2",
            location_name="Science Wing",
            status="offline",
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=9),
            department_id="dept_municipal_demo",
            external_id="CAM_DEMO_03",
            district="Vadodara",
            zone="Sayajigunj",
            latitude=22.3072,
            longitude=73.1812,
            camera_type="fixed",
            vendor="Sample Municipal VMS",
            model="Sample-01",
            protocol="RTSP",
            stream_status="OFFLINE",
            health_status=HealthStatus.offline,
            is_demo=True,
        ),
    ]
    if get_settings().demo_runtime_only:
        vms_a.base_url = "http://127.0.0.1:8091"
        vms_b.base_url = "http://127.0.0.1:8092"
        vms_a.status = vms_b.status = ConnectorStatus.unknown
        _ensure_local_op_camera(db, org.id)
        # Identity, department/VMS configuration, and local AI camera sources
        # are bootstrapped. Observations, watchlists, and alerts use their APIs.
        db.commit()
        return
    db.add_all(cameras)

    zones = [
        Zone(
            id="zone_gate_entry",
            org_id=org.id,
            camera_id="cam_gate_1",
            name="Entrance Boundary",
            zone_type="restricted",
            polygon={"points": [{"x": 0.05, "y": 0.2}, {"x": 0.95, "y": 0.2}, {"x": 0.95, "y": 0.95}, {"x": 0.05, "y": 0.95}]},
        ),
        Zone(
            id="zone_hallway_crowd",
            org_id=org.id,
            camera_id="cam_hallway",
            name="Hallway Crowd Zone",
            zone_type="corridor",
            polygon={"points": [{"x": 0.0, "y": 0.25}, {"x": 1.0, "y": 0.25}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}]},
            crowd_threshold=35,
        ),
    ]
    db.add_all(zones)

    rules = [
        AlertRule(
            org_id=org.id,
            name="Critical intrusion",
            event_type=EventType.intrusion,
            confidence_threshold=0.70,
            notify_channels=["whatsapp", "email"],
            notify_user_ids=["usr_principal", "usr_security"],
            suppress_duration_sec=60,
        ),
        AlertRule(
            org_id=org.id,
            name="Crowd in hallway",
            event_type=EventType.crowd,
            confidence_threshold=0.65,
            condition_type="crowd_threshold",
            condition_value=35,
            notify_channels=["whatsapp"],
            notify_user_ids=["usr_principal"],
            suppress_duration_sec=180,
        ),
        AlertRule(
            org_id=org.id,
            name="Camera health",
            event_type=EventType.camera_offline,
            confidence_threshold=0.5,
            notify_channels=["email"],
            notify_user_ids=["usr_security"],
            suppress_duration_sec=300,
        ),
    ]
    db.add_all(rules)

    event = Event(
        id="evt_demo_crowd",
        org_id=org.id,
        camera_id="cam_hallway",
        edge_server_id=edge.id,
        zone_id="zone_hallway_crowd",
        type=EventType.crowd,
        confidence=0.91,
        snapshot_url="/demo/snapshots/crowd.svg",
        metadata_json={"person_count": 48, "threshold": 35, "duration_seconds": 12},
        alert_sent=True,
    )
    db.add(event)
    db.flush()
    db.add(
        NotificationLog(
            org_id=org.id,
            event_id=event.id,
            alert_rule_id=rules[1].id,
            user_id=admin.id,
            channel="whatsapp",
            recipient=admin.whatsapp_phone or "",
            status="sent",
            message="SURAKSH DEMO: Crowd event metadata received.",
        )
    )
    watchlist = Watchlist(id="watchlist_demo", department_id="dept_transport_demo", name="Priority vehicle list - DEMO", description="Synthetic hackathon watchlist", created_by=admin.id, active=True)
    db.add(watchlist)
    db.add(WatchlistEntry(id="watch_entry_demo", watchlist_id=watchlist.id, plate_text="GJ01AB1234", priority="high", reason="Synthetic test record", active=True))
    db.add(DetectionEvent(id="detection_demo_a", camera_id="cam_gate_1", department_id="dept_home_demo", source_system="VMS_A", detected_at=datetime.now(timezone.utc) - timedelta(minutes=11), vehicle_class="car", vehicle_confidence=0.94, plate_text="GJ01AB1234", plate_confidence=0.88, latitude=23.0225, longitude=72.5714, metadata_json={"source_notice": "DEMO"}, is_demo=True))
    db.commit()
