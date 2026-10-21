import uuid
import secrets
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/api/pairing", tags=["Pairing"])

@router.post("/invitations")
def create_invitation(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    # If user already has a pending relationship, reuse or renew its invite code
    if user.relationship_id:
        existing_rel = db.query(models.Relationship).filter(models.Relationship.id == user.relationship_id).first()
        if existing_rel and existing_rel.status == "pending":
            if not existing_rel.invite_code:
                existing_rel.invite_code = secrets.token_hex(3).upper()
                db.commit()
            return {"invite_code": existing_rel.invite_code, "relationship_id": existing_rel.id}

    invite_code = secrets.token_hex(3).upper() # 6 characters
    rel = models.Relationship(id=str(uuid.uuid4()), invite_code=invite_code, status="pending")
    db.add(rel)
    user.relationship_id = rel.id
    db.commit()
    return {"invite_code": invite_code, "relationship_id": rel.id}

@router.post("/accept")
def accept_invitation(
    invite_code: str = Form(...),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    code = invite_code.strip().upper()
    rel = db.query(models.Relationship).filter(models.Relationship.invite_code == code).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Invalid or expired invite code")

    # Find who already belongs to this relationship
    existing_members = db.query(models.User).filter(models.User.relationship_id == rel.id).all()
    
    # Don't let a user pair with themselves
    if any(m.id == user.id for m in existing_members):
        raise HTTPException(status_code=400, detail="You cannot pair with your own invite code")

    if len(existing_members) >= 2:
        raise HTTPException(status_code=400, detail="This couple space is already full")

    # If Partner B had previously created an empty pending relationship, clean it up
    if user.relationship_id and user.relationship_id != rel.id:
        old_rel = db.query(models.Relationship).filter(models.Relationship.id == user.relationship_id).first()
        if old_rel and old_rel.status == "pending":
            db.delete(old_rel)

    # Attach Partner B to the relationship
    user.relationship_id = rel.id
    rel.status = "active"
    rel.invite_code = None  # Consume the code
    db.commit()

    partner = existing_members[0] if existing_members else None
    return {
        "status": "paired",
        "relationship_id": rel.id,
        "partner_name": partner.display_name if partner else "Partner"
    }

@router.get("/status")
def get_pairing_status(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not user.relationship_id:
        return {"is_paired": False, "status": "unpaired", "partner_name": None}

    rel = db.query(models.Relationship).filter(models.Relationship.id == user.relationship_id).first()
    if not rel:
        return {"is_paired": False, "status": "unpaired", "partner_name": None}

    # Direct database query for the partner (avoiding lazy-load bugs)
    partner = db.query(models.User).filter(
        models.User.relationship_id == rel.id,
        models.User.id != user.id
    ).first()

    if partner and rel.status == "active":
        return {
            "is_paired": True,
            "status": "active",
            "partner_name": partner.display_name,
            "relationship_id": rel.id
        }
    else:
        return {
            "is_paired": False,
            "status": "pending",
            "invite_code": rel.invite_code,
            "partner_name": None
        }
