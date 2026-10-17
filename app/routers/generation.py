import uuid
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/api/generation-jobs", tags=["Generation"])

@router.post("")
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

@router.get("/{job_id}")
def get_job(
    job_id: str,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    job = db.query(models.GenerationJob).filter(
        models.GenerationJob.id == job_id,
        models.GenerationJob.relationship_id == user.relationship_id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status_str = job.status.value if hasattr(job.status, "value") else str(job.status)
    return {
        "id": job.id,
        "job_id": job.id,
        "status": status_str,
        "result_image_id": job.result_image_id,
        "error_code": job.error_code
    }
