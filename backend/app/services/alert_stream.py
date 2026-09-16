"""Database-backed SSE cursor. Only committed alerts are visible to readers.

This local-demo transport polls with short-lived DB sessions, so reconnects and
multiple backend workers share durable history rather than an in-memory queue.
"""
from sqlalchemy import and_, or_
from app.models.entities import Alert, Camera, Department, DetectionEvent


def alert_query(db, org_id):
    return db.query(Alert).join(Department, Department.id == Alert.department_id).filter(Department.org_id == org_id)


def alert_out(db, alert):
    detection = db.get(DetectionEvent, alert.detection_id)
    camera = db.get(Camera, detection.camera_id)
    department = db.get(Department, alert.department_id)
    return {"id": alert.id, "detection_id": alert.detection_id,
            "watchlist_entry_id": alert.watchlist_entry_id, "priority": alert.priority,
            "status": alert.status, "created_at": alert.created_at.isoformat(),
            "plate_text": detection.plate_text, "camera_id": camera.id,
            "camera_name": camera.name, "department": department.name,
            "source_system": detection.source_system, "district": camera.district,
            "location": camera.zone, "detected_at": detection.detected_at.isoformat(),
            "vehicle_confidence": detection.vehicle_confidence,
            "plate_confidence": detection.plate_confidence, "is_demo": detection.is_demo}


def read_after(db, org_id, cursor, limit=100):
    query = alert_query(db, org_id)
    if cursor:
        timestamp, item_id = cursor
        query = query.filter(or_(Alert.created_at > timestamp,
                               and_(Alert.created_at == timestamp, Alert.id > item_id)))
    return query.order_by(Alert.created_at, Alert.id).limit(limit).all()
