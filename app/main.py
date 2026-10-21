import os
import uuid
import secrets
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import Base, engine, get_db
from app import models, auth, collage
from app.prompts import generate_flexible_prompt

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LAVA Couple Space API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.abspath("./uploads")
COLLAGE_DIR = os.path.abspath("./collages")
GENERATED_DIR = os.path.abspath("./generated")
for p in [UPLOAD_DIR, COLLAGE_DIR, GENERATED_DIR]:
    os.makedirs(p, exist_ok=True)

WORKER_SECRET = os.getenv("WORKER_SECRET", "my-super-private-couple-secret-2026")

@app.get("/")
def root():
    return {"app": "LAVA Couple Space API", "status": "online", "version": "1.0.0"}

# ----------------- AUTHENTICATION -----------------
@app.post("/api/auth/register")
def register(
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    db: Session = Depends(get_db)
):
    clean_username = username.strip().lower()
    if db.query(models.User).filter(models.User.username == clean_username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user = models.User(
        id=str(uuid.uuid4()),
        username=clean_username,
        display_name=display_name.strip(),
        password_hash=auth.get_password_hash(password)
    )
    db.add(user)
    db.commit()
    token = auth.create_access_token(user.id)
    return {"access_token": token, "token": token, "token_type": "bearer", "user_id": user.id, "display_name": user.display_name}

@app.post("/api/auth/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    clean_username = form_data.username.strip().lower()
    user = db.query(models.User).filter(models.User.username == clean_username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid username or password")
    
    token = auth.create_access_token(user.id)
    return {"access_token": token, "token": token, "token_type": "bearer", "user_id": user.id, "display_name": user.display_name}

# ----------------- PAIRING ENGINE -----------------
@app.post("/api/pairing/invitations")
def create_invitation(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    # If user already belongs to an active relationship with a partner, return existing
    if user.relationship_id:
        existing_rel = db.query(models.Relationship).filter(models.Relationship.id == user.relationship_id).first()
        if existing_rel:
            if existing_rel.status == "active":
                return {"invite_code": "ALREADY_PAIRED", "relationship_id": existing_rel.id}
            if existing_rel.status == "pending" and existing_rel.invite_code:
                return {"invite_code": existing_rel.invite_code, "relationship_id": existing_rel.id}

    new_code = secrets.token_hex(3).upper() # 6 characters
    rel = models.Relationship(id=str(uuid.uuid4()), invite_code=new_code, status="pending")
    db.add(rel)
    user.relationship_id = rel.id
    db.commit()
    return {"invite_code": new_code, "relationship_id": rel.id}

@app.post("/api/pairing/accept")
def accept_invitation(
    invite_code: str = Form(...),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    code = invite_code.strip().upper()
    rel = db.query(models.Relationship).filter(models.Relationship.invite_code == code).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Invalid or expired invite code")

    # Prevent pairing with yourself
    creator = db.query(models.User).filter(models.User.relationship_id == rel.id).first()
    if creator and creator.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot pair with your own invite code")

    # Clean up any leftover pending relationship Partner B might have created earlier
    if user.relationship_id and user.relationship_id != rel.id:
        old_rel = db.query(models.Relationship).filter(models.Relationship.id == user.relationship_id).first()
        if old_rel and old_rel.status == "pending":
            db.delete(old_rel)

    user.relationship_id = rel.id
    rel.status = "active"
    rel.invite_code = None  # Consume invite code
    db.commit()

    return {"status": "paired", "relationship_id": rel.id, "partner_name": creator.display_name if creator else "Partner"}

@app.get("/api/pairing/status")
def get_pairing_status(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not user.relationship_id:
        return {"is_paired": False, "status": "unpaired", "partner_name": None, "invite_code": None}

    rel = db.query(models.Relationship).filter(models.Relationship.id == user.relationship_id).first()
    if not rel:
        return {"is_paired": False, "status": "unpaired", "partner_name": None, "invite_code": None}

    # Direct query for partner across all sessions
    partner = db.query(models.User).filter(
        models.User.relationship_id == rel.id,
        models.User.id != user.id
    ).first()

    if partner and rel.status == "active":
        return {
            "is_paired": True,
            "status": "active",
            "partner_name": partner.display_name,
            "relationship_id": rel.id,
            "invite_code": None
        }
    else:
        return {
            "is_paired": False,
            "status": "pending",
            "invite_code": rel.invite_code,
            "partner_name": None,
            "relationship_id": rel.id
        }

# ----------------- EMOTIONS & AFFECTION -----------------
@app.post("/api/emotions")
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
        note=note.strip() if note else None
    )
    db.add(entry)
    db.commit()
    return {"status": "sent", "id": entry.id}

@app.get("/api/emotions")
def list_emotions(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not user.relationship_id:
        return []
    
    entries = db.query(models.EmotionEntry).filter(
        models.EmotionEntry.relationship_id == user.relationship_id
    ).order_by(models.EmotionEntry.created_at.desc()).limit(30).all()

    result = []
    for e in entries:
        author = db.query(models.User).filter(models.User.id == e.author_id).first()
        result.append({
            "id": e.id,
            "emotion_type": e.emotion_type,
            "note": e.note,
            "created_at": e.created_at.isoformat(),
            "is_me": (e.author_id == user.id),
            "author_name": author.display_name if author else "Partner"
        })
    return result

# ----------------- SHARED GALLERY & UPLOADS -----------------
@app.post("/api/gallery/upload")
async def upload_image(
    file: UploadFile = File(...),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not user.relationship_id:
        raise HTTPException(status_code=400, detail="User is not paired")

    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    filename = f"upload_{user.id[:6]}_{uuid.uuid4().hex[:8]}.{ext}"
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

    # Automatically queue permutations with partner's photos
    partner = db.query(models.User).filter(
        models.User.relationship_id == user.relationship_id,
        models.User.id != user.id
    ).first()

    queued_count = 0
    if partner:
        partner_photos = db.query(models.GalleryImage).filter(
            models.GalleryImage.relationship_id == user.relationship_id,
            models.GalleryImage.creator_id == partner.id,
            models.GalleryImage.source_type == "upload"
        ).all()

        for p_img in partner_photos:
            job = models.GenerationJob(
                id=str(uuid.uuid4()),
                relationship_id=user.relationship_id,
                requester_id=user.id,
                prompt=generate_flexible_prompt(),
                ref_image_1_filename=new_img.storage_filename,
                ref_image_2_filename=p_img.storage_filename,
                status=models.JobStatus.QUEUED
            )
            db.add(job)
            queued_count += 1

        db.commit()

    return {"id": new_img.id, "filename": filename, "permutations_queued": queued_count}

@app.get("/api/gallery")
def get_gallery(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not user.relationship_id:
        return []
    
    images = db.query(models.GalleryImage).filter(
        models.GalleryImage.relationship_id == user.relationship_id
    ).order_by(models.GalleryImage.created_at.desc()).all()

    return [
        {
            "id": img.id,
            "filename": img.storage_filename,
            "source_type": img.source_type,
            "created_at": img.created_at.isoformat(),
            "url": f"/api/gallery/file/{img.storage_filename}"
        }
        for img in images
    ]

@app.get("/api/gallery/file/{filename}")
def serve_file(filename: str):
    for folder in [UPLOAD_DIR, GENERATED_DIR, COLLAGE_DIR]:
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="Image not found")

@app.get("/api/gallery/recent-collage")
def get_recent_collage(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not user.relationship_id:
        raise HTTPException(status_code=400, detail="User is not paired")
    images = db.query(models.GalleryImage).filter(
        models.GalleryImage.relationship_id == user.relationship_id
    ).order_by(models.GalleryImage.created_at.desc()).limit(3).all()
    if not images:
        return {"collage_url": None}

    img_paths = [os.path.join(UPLOAD_DIR if img.source_type == "upload" else GENERATED_DIR, img.storage_filename) for img in images]
    existing_paths = [p for p in img_paths if os.path.exists(p)]
    if not existing_paths:
        return {"collage_url": None}

    collage_filename = f"collage_{user.relationship_id[:8]}.jpg"
    collage_path = os.path.join(COLLAGE_DIR, collage_filename)
    try:
        from app.collage import create_three_photo_collage
        create_three_photo_collage(existing_paths, collage_path)
        return {"collage_url": f"/api/gallery/file/{collage_filename}"}
    except Exception as e:
        return {"collage_url": None, "error": str(e)}

# ----------------- GENERATION JOBS -----------------
@app.post("/api/generation-jobs")
def create_job(
    prompt: str = Form(...),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if not user.relationship_id:
        raise HTTPException(status_code=400, detail="User is not paired")
    job = models.GenerationJob(
        id=str(uuid.uuid4()),
        relationship_id=user.relationship_id,
        requester_id=user.id,
        prompt=prompt,
        status=models.JobStatus.QUEUED
    )
    db.add(job)
    db.commit()
    return {"job_id": job.id, "status": job.status.value if hasattr(job.status, "value") else str(job.status)}

@app.get("/api/generation-jobs/{job_id}")
def get_job(
    job_id: str,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    job = db.query(models.GenerationJob).filter(models.GenerationJob.id == job_id).first()
    if not job or job.relationship_id != user.relationship_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "result_image_id": job.result_image_id,
        "error_code": job.error_code
    }

# ----------------- WORKER CLOUD BRIDGE -----------------
@app.get("/api/worker/claim-job")
def claim_job(secret: str, db: Session = Depends(get_db)):
    if secret != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")

    job = db.query(models.GenerationJob).filter(models.GenerationJob.status == models.JobStatus.QUEUED).first()
    if not job:
        return {"has_job": False}

    job.status = models.JobStatus.RUNNING
    db.commit()

    return {
        "has_job": True,
        "job_id": job.id,
        "prompt": job.prompt,
        "relationship_id": job.relationship_id,
        "requester_id": job.requester_id,
        "ref_image_1_url": f"/api/gallery/file/{job.ref_image_1_filename}" if job.ref_image_1_filename else None,
        "ref_image_2_url": f"/api/gallery/file/{job.ref_image_2_filename}" if job.ref_image_2_filename else None
    }

@app.post("/api/worker/submit-job")
async def submit_job(
    secret: str = Form(...),
    job_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if secret != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")

    job = db.query(models.GenerationJob).filter(models.GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    filename = f"couple_gen_{uuid.uuid4().hex[:10]}.jpg"
    filepath = os.path.join(GENERATED_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(await file.read())

    gallery_img = models.GalleryImage(
        id=str(uuid.uuid4()),
        relationship_id=job.relationship_id,
        creator_id=job.requester_id,
        storage_filename=filename,
        source_type="ai_generated"
    )
    db.add(gallery_img)
    job.result_image_id = gallery_img.id
    job.status = models.JobStatus.SUCCEEDED
    db.commit()

    return {"status": "saved", "gallery_id": gallery_img.id}

@app.post("/api/worker/fail-job")
def fail_job(
    secret: str = Form(...),
    job_id: str = Form(...),
    error_code: str = Form("CLIENT_GEN_FAILED"),
    db: Session = Depends(get_db)
):
    if secret != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")

    job = db.query(models.GenerationJob).filter(models.GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = models.JobStatus.FAILED
    job.error_code = error_code
    db.commit()

    return {"status": "failed", "job_id": job.id}
