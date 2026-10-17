import uuid
import secrets
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/api/pairing", tags=["Pairing"])

@router.post("/invitations")
def create_invitation(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    invite_code = secrets.token_hex(3).upper() # 6 characters
    rel = models.Relationship(id=str(uuid.uuid4()), invite_code=invite_code, status="pending")
    db.add(rel)
    user.relationship_id = rel.id
    db.commit()
    return {"invite_code": invite_code, "relationship_id": rel.id}

@router.post("/accept")
def accept_invitation(invite_code: str = Form(...), user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    rel = db.query(models.Relationship).filter(models.Relationship.invite_code == invite_code.strip().upper()).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Invalid or expired invite code")
    if len(rel.members) >= 2:
        raise HTTPException(status_code=400, detail="This couple space is already full")
    
    user.relationship_id = rel.id
    rel.status = "active"
    rel.invite_code = None  # Consume invite code
    db.commit()
    return {"status": "paired", "relationship_id": rel.id}
