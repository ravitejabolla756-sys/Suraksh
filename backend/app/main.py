from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alert_rules, analytics, auth, cameras, events, leads, notifications, users
from app.api import audit, detections, registry, realtime, demo_media, safety_incidents
from app.core.config import get_settings
from app.models.database import SessionLocal
from app.services.seed import seed_demo


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.demo_seed:
        db = SessionLocal()
        try:
            seed_demo(db)
        finally:
            db.close()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(events.router)
app.include_router(alert_rules.router)
app.include_router(analytics.router)
app.include_router(leads.router)
app.include_router(notifications.router)
app.include_router(users.router)
app.include_router(cameras.department_router)
app.include_router(cameras.vms_router)
app.include_router(detections.router)
app.include_router(registry.router)
app.include_router(audit.router)
app.include_router(realtime.router)
app.include_router(demo_media.router)
app.include_router(safety_incidents.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "suraksh-backend"}
