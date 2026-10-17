from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models import JobStatus

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserRegister(BaseModel):
    username: str
    password: str
    display_name: str

class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    relationship_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class InvitationResponse(BaseModel):
    invite_code: str
    relationship_id: str

class PairingResponse(BaseModel):
    status: str
    relationship_id: str

class EmotionCreate(BaseModel):
    emotion_type: str
    note: Optional[str] = None

class EmotionResponse(BaseModel):
    id: str
    emotion_type: str
    note: Optional[str] = None
    created_at: datetime
    relationship_id: Optional[str] = None
    author_id: Optional[str] = None

    class Config:
        from_attributes = True

class GalleryImageResponse(BaseModel):
    id: str
    filename: str
    source: str
    created_at: datetime

    class Config:
        from_attributes = True

class CollageResponse(BaseModel):
    collage_url: str

class JobCreate(BaseModel):
    prompt: str

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    result_image_id: Optional[str] = None
    error_code: Optional[str] = None
