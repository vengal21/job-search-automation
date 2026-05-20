from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(String, default="user") # 'user' or 'admin'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    is_default = Column(Boolean, default=False)
    
    # Structured parsed data
    candidate_name = Column(String)
    phone = Column(String)
    location = Column(String)
    total_experience = Column(Float)
    summary = Column(Text)
    
    # Store complex lists as JSON
    roles = Column(JSON, default=list)
    skills = Column(JSON, default=list)
    technical_skills = Column(JSON, default=list)
    soft_skills = Column(JSON, default=list)
    projects = Column(JSON, default=list)
    certifications = Column(JSON, default=list)
    education = Column(JSON, default=list)
    tools = Column(JSON, default=list)
    ats_keywords = Column(JSON, default=list)
    
    confidence_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="resumes")
    chunks = relationship("ResumeChunk", back_populates="resume", cascade="all, delete-orphan")

class ResumeChunk(Base):
    """Stores text chunks for RAG. Actual embeddings go to ChromaDB mapped by this ID."""
    __tablename__ = "resume_chunks"
    id = Column(String, primary_key=True, index=True) # UUID
    resume_id = Column(Integer, ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer)
    
    resume = relationship("Resume", back_populates="chunks")

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, index=True) # External ID or UUID
    company_name = Column(String, index=True)
    title = Column(String, index=True)
    location = Column(String)
    salary = Column(String)
    description = Column(Text)
    skills_required = Column(JSON, default=list)
    experience_required = Column(String)
    source = Column(String)
    job_url = Column(String)
    posted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    applications = relationship("Application", back_populates="job")

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    
    status = Column(String, default="pending") # pending, applied, failed, rejected
    match_score = Column(Float)
    ats_score = Column(Float)
    missing_skills = Column(JSON, default=list)
    applied_at = Column(DateTime(timezone=True))
    
    user = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")
