import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, 
    Text, Enum as SQLEnum, Boolean
)
from sqlalchemy.orm import relationship as sa_relationship
from app.database import Base

def get_utc_now():
    return datetime.now(timezone.utc)

class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    fcm_token = Column(String(255), nullable=True)
    relationship_id = Column(String(36), ForeignKey("relationships.id"), nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    relationship = sa_relationship("Relationship", back_populates="members", foreign_keys=[relationship_id])
    sent_emotions = sa_relationship("EmotionEntry", back_populates="author")

class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(String(36), primary_key=True, index=True)
    invite_code = Column(String(8), unique=True, index=True, nullable=True)
    status = Column(String(20), default="active")  # pending, active, unpaired
    created_at = Column(DateTime, default=get_utc_now)

    members = sa_relationship("User", back_populates="relationship", foreign_keys="[User.relationship_id]")
    emotions = sa_relationship("EmotionEntry", back_populates="rel", cascade="all, delete-orphan")
    images = sa_relationship("GalleryImage", back_populates="rel", cascade="all, delete-orphan")
    jobs = sa_relationship("GenerationJob", back_populates="rel", cascade="all, delete-orphan")

class EmotionEntry(Base):
    __tablename__ = "emotion_entries"

    id = Column(String(36), primary_key=True, index=True)
    relationship_id = Column(String(36), ForeignKey("relationships.id"), nullable=False)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    emotion_type = Column(String(50), nullable=False) # e.g. "missing_you", "warm", "loving"
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    rel = sa_relationship("Relationship", back_populates="emotions")
    author = sa_relationship("User", back_populates="sent_emotions")

class GalleryImage(Base):
    __tablename__ = "gallery_images"

    id = Column(String(36), primary_key=True, index=True)
    relationship_id = Column(String(36), ForeignKey("relationships.id"), nullable=False)
    creator_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    storage_filename = Column(String(255), nullable=False)
    source_type = Column(String(20), default="upload") # "upload" | "ai_generated"
    created_at = Column(DateTime, default=get_utc_now)

    rel = sa_relationship("Relationship", back_populates="images")

class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(String(36), primary_key=True, index=True)
    relationship_id = Column(String(36), ForeignKey("relationships.id"), nullable=False)
    requester_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    prompt = Column(Text, nullable=False)
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False)
    
    # Track the exact pair of photos being combined
    ref_image_1_filename = Column(String(255), nullable=True)
    ref_image_2_filename = Column(String(255), nullable=True)
    result_image_id = Column(String(36), ForeignKey("gallery_images.id"), nullable=True)
    error_code = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    rel = sa_relationship("Relationship", back_populates="jobs")

