import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from app.api.deps import bearer, current_user
from app.models.database import SessionLocal
from app.models.entities import Alert
from app.services.alert_stream import alert_query, alert_out, read_after

router = APIRouter(tags=["alerts"])


def read_batch(org_id, cursor):
    with SessionLocal() as db:
        rows = read_after(db, org_id, cursor)
        return [(a.created_at, a.id, alert_out(db, a)) for a in rows]


@router.get("/alerts/stream")
def stream_alerts(request: Request, after: str | None = None,
                  last_event_id: str | None = Header(default=None), credentials=Depends(bearer)):
    resume_id = after or last_event_id
    with SessionLocal() as db:
        # Do not retain an authentication DB connection for an entire SSE session.
        org_id = current_user(credentials, db).org_id
        if resume_id:
            row = alert_query(db, org_id).filter(Alert.id == resume_id).first()
            if not row:
                raise HTTPException(404, "Alert cursor not found")
        else:
            row = alert_query(db, org_id).order_by(Alert.created_at.desc(), Alert.id.desc()).first()
        cursor = (row.created_at, row.id) if row else (datetime.min, "")

    async def events():
        nonlocal cursor
        yield 'event: ready\ndata: {"status":"connected"}\n\n'
        idle = 0
        while not await request.is_disconnected():
            rows = await run_in_threadpool(read_batch, org_id, cursor)
            for timestamp, item_id, data in rows:
                cursor = (timestamp, item_id)
                yield f'id: {item_id}\nevent: alert\ndata: {json.dumps(data)}\n\n'
            idle += 1
            if idle % 20 == 0:
                yield ': heartbeat\n\n'
            await asyncio.sleep(0.5)
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
