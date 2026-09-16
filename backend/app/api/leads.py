from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.models.database import get_db
from app.models.entities import PilotLead, User
from app.schemas.dto import PilotLeadCreate, PilotLeadOut, PilotLeadUpdate


router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=PilotLeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(payload: PilotLeadCreate, db: Session = Depends(get_db)):
    lead = PilotLead(
        school_name=payload.school_name.strip(),
        email=payload.email.lower(),
        phone=payload.phone.strip(),
        city=payload.city.strip(),
        camera_count=payload.camera_count,
        source=payload.source,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@router.get("", response_model=list[PilotLeadOut])
def list_leads(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(PilotLead).order_by(PilotLead.created_at.desc()).limit(100).all()


@router.patch("/{lead_id}", response_model=PilotLeadOut)
def update_lead(
    lead_id: str,
    payload: PilotLeadUpdate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lead = db.get(PilotLead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    lead.status = payload.status
    if payload.notes is not None:
        lead.notes = payload.notes
    db.commit()
    db.refresh(lead)
    return lead
