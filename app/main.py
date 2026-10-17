import os
import uuid
from fastapi import FastAPI, Depends, HTTPException, Form, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import Base, engine, get_db
from app.storage import init_storage_directories, GENERATED_DIR
from app import models, auth
from app.routers import pairing, emotions, gallery, generation

Base.metadata.create_all(bind=engine)
init_storage_directories()

app = FastAPI(title="Couple Space API", version="0.2.0")

WORKER_SECRET = os.getenv("WORKER_SECRET", "my-super-private-couple-secret-2026")

@app.get("/")
def root():
    return {"app": "Couple Space API", "status": "online", "version": "0.2.0"}

# ----------------- AUTH -----------------
@app.post("/api/auth/register")
def register(
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    db: Session = Depends(get_db)
):
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = models.User(
        id=str(uuid.uuid4()),
        username=username,
        display_name=display_name,
        password_hash=auth.get_password_hash(password)
    )
    db.add(user)
    db.commit()
    token = auth.create_access_token(user.id)
    return {
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "display_name": user.display_name
    }

@app.post("/api/auth/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid username or password")
    token = auth.create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "display_name": user.display_name
    }

# ----------------- WORKER BRIDGE ENDPOINTS -----------------
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
async def submit_completed_job(
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

    filename = f"gen_cloud_{uuid.uuid4().hex[:10]}.jpg"
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

# ----------------- INCLUDE ROUTERS -----------------
app.include_router(pairing.router)
app.include_router(emotions.router)
app.include_router(gallery.router)
app.include_router(generation.router)
