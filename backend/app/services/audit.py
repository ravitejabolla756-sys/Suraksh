from app.models.entities import AuditLog


def record(db, org_id, action, resource_type, resource_id, user_id=None, **values):
    """Record the action in the caller's transaction; never commit independently."""
    db.add(AuditLog(org_id=org_id, user_id=user_id, action=action,
                    resource_type=resource_type, resource_id=resource_id,
                    new_values={"result": "success", **values}))
