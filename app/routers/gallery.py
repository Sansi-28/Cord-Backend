import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.storage import UPLOAD_DIR, GENERATED_DIR, COLLAGE_DIR, resolve_file_path
from app import models, auth, collage
from app.prompts import generate_flexible_prompt

router = APIRouter(prefix="/api/gallery", tags=["Gallery"])

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    note: str = Form(None),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not user.relationship_id:
        raise HTTPException(status_code=400, detail="User is not paired")

    # 1. Save uploaded photo
    ext = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else "jpg"
    filename = f"upload_{user.id[:8]}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(await file.read())

    new_img = models.GalleryImage(
        id=str(uuid.uuid4()),
        relationship_id=user.relationship_id,
        creator_id=user.id,
        storage_filename=filename,
        source_type="upload"
    )
    db.add(new_img)
    db.commit()

    # 2. Find the other partner in the relationship
    rel = db.query(models.Relationship).filter(models.Relationship.id == user.relationship_id).first()
    other_partner = next((m for m in rel.members if m.id != user.id), None) if rel and rel.members else None

    queued_permutations = 0
    if other_partner:
        # Fetch all uploaded photos from the other partner
        partner_photos = db.query(models.GalleryImage).filter(
            models.GalleryImage.relationship_id == rel.id,
            models.GalleryImage.creator_id == other_partner.id,
            models.GalleryImage.source_type == "upload"
        ).all()

        # 3. Create permutation jobs: (new_img + each photo of partner)
        for partner_photo in partner_photos:
            job = models.GenerationJob(
                id=str(uuid.uuid4()),
                relationship_id=rel.id,
                requester_id=user.id,
                prompt=generate_flexible_prompt(note),
                ref_image_1_filename=new_img.storage_filename,
                ref_image_2_filename=partner_photo.storage_filename,
                status=models.JobStatus.QUEUED
            )
            db.add(job)
            queued_permutations += 1

        db.commit()

    return {
        "status": "uploaded",
        "id": new_img.id,
        "image_id": new_img.id,
        "filename": filename,
        "permutations_queued": queued_permutations
    }

@router.get("")
def get_gallery(
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not user.relationship_id:
        return []
    images = db.query(models.GalleryImage).filter(
        models.GalleryImage.relationship_id == user.relationship_id
    ).order_by(models.GalleryImage.created_at.desc()).all()
    return [
        {
            "id": img.id,
            "filename": img.storage_filename,
            "source": img.source_type,
            "created_at": img.created_at.isoformat() if img.created_at else ""
        }
        for img in images
    ]

@router.get("/file/{filename}")
def get_file(filename: str):
    file_path = resolve_file_path(filename)
    if file_path:
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")

@router.get("/recent-collage")
def get_recent_collage(
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Creates a 3-image Pinterest-style collage from the couple's 3 most recent pictures."""
    if not user.relationship_id:
        raise HTTPException(status_code=400, detail="User not paired")
    images = db.query(models.GalleryImage).filter(
        models.GalleryImage.relationship_id == user.relationship_id
    ).order_by(models.GalleryImage.created_at.desc()).limit(3).all()

    if not images:
        raise HTTPException(status_code=404, detail="No images to form collage")

    paths = []
    for img in images:
        p = os.path.join(GENERATED_DIR if img.source_type == "ai_generated" else UPLOAD_DIR, img.storage_filename)
        if os.path.exists(p):
            paths.append(p)

    if not paths:
        raise HTTPException(status_code=404, detail="Underlying image files not found")

    collage_filename = f"collage_{user.relationship_id}_{len(paths)}.png"
    collage_path = os.path.join(COLLAGE_DIR, collage_filename)
    collage.create_pinterest_collage(paths, collage_path)
    return {"collage_url": f"/api/gallery/file/{collage_filename}"}
