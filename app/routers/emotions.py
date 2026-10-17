import uuid
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/api/emotions", tags=["Emotions"])

@router.post("")
def send_emotion(
    emotion_type: str = Form(...),
    note: str = Form(None),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not user.relationship_id:
        raise HTTPException(status_code=400, detail="User is not paired")
    entry = models.EmotionEntry(
        id=str(uuid.uuid4()),
        relationship_id=user.relationship_id,
        author_id=user.id,
        emotion_type=emotion_type,
        note=note
    )
    db.add(entry)
    db.commit()
    return {"status": "sent", "id": entry.id}

@router.get("")
def get_emotions(
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not user.relationship_id:
        return []
    entries = db.query(models.EmotionEntry).filter(
        models.EmotionEntry.relationship_id == user.relationship_id
    ).order_by(models.EmotionEntry.created_at.desc()).limit(20).all()

    return [
        {
            "id": e.id,
            "relationship_id": e.relationship_id,
            "author_id": e.author_id,
            "emotion_type": e.emotion_type,
            "note": e.note,
            "created_at": e.created_at.isoformat() if e.created_at else ""
        }
        for e in entries
    ]
