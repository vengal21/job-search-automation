import logging
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, Date, DateTime, Boolean, create_engine, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker

from config import MYSQL_URI

logger = logging.getLogger(__name__)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User(username='{self.username}')>"

class SearchSession(Base):
    __tablename__ = "search_sessions"
    job_id = Column(String(50), primary_key=True) # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    search_params = Column(Text, nullable=True) # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SearchSession(job_id='{self.job_id}', user_id={self.user_id})>"


class JobResult(Base):
    __tablename__ = "job_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(50), nullable=False, index=True) # links to the search job_id UUID
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    salary_string = Column(String(100), nullable=True)
    source = Column(String(50), nullable=False)
    match_score = Column(Integer, default=0)
    match_grade = Column(String(5), nullable=True)
    job_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    date_posted = Column(Date, nullable=True)
    search_term = Column(String(255), nullable=True)
    is_remote = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    applied_status = Column(Boolean, default=False)

    def __repr__(self):
        return f"<JobResult(id={self.id}, title='{self.title}', company='{self.company}')>"

class UserAnswer(Base):
    __tablename__ = "user_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_text = Column(Text, nullable=False, index=True)
    answer_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<UserAnswer(id={self.id})>"

class UserResume(Base):
    __tablename__ = "user_resumes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    filename = Column(String(255), nullable=False)
    skills = Column(Text, nullable=True) # stored as JSON list
    suggested_titles = Column(Text, nullable=True) # stored as JSON list
    experience_years = Column(Float, default=1.5)
    summary = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<UserResume(user_id={self.user_id}, filename='{self.filename}')>"

class DeletedSearchSession(Base):
    __tablename__ = "deleted_search_sessions"
    job_id = Column(String(50), primary_key=True)
    user_id = Column(Integer, nullable=False)
    search_params = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, default=datetime.utcnow)

class DeletedJobResult(Base):
    __tablename__ = "deleted_job_results"
    id = Column(Integer, primary_key=True)
    job_id = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    salary_string = Column(String(100), nullable=True)
    source = Column(String(50), nullable=False)
    match_score = Column(Integer, default=0)
    match_grade = Column(String(5), nullable=True)
    job_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    date_posted = Column(Date, nullable=True)
    search_term = Column(String(255), nullable=True)
    is_remote = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=True)
    applied_status = Column(Boolean, default=False)
    deleted_at = Column(DateTime, default=datetime.utcnow)

# Global engine and session factory
engine = None
SessionLocal = None

def init_db():
    """Initialize the MySQL database connection and create tables if they do not exist."""
    global engine, SessionLocal
    try:
        engine = create_engine(MYSQL_URI, echo=False)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info(f"MySQL database initialized successfully with URI: {MYSQL_URI}")
    except Exception as e:
        logger.error(f"Failed to initialize MySQL database: {e}")

def save_jobs_to_db(search_job_id: str, jobs: list[dict]):
    """Save a list of job dictionaries to the database using the JobResult model."""
    if not SessionLocal:
        logger.error("Database not initialized. Cannot save jobs.")
        return

    session = SessionLocal()
    try:
        db_jobs = []
        for job in jobs:
            db_job = JobResult(
                job_id=search_job_id,
                title=job.get("title", ""),
                company=job.get("company", ""),
                location=job.get("location", ""),
                salary_string=job.get("salary_string", ""),
                source=job.get("source", ""),
                match_score=job.get("match_score", 0),
                match_grade=job.get("match_grade", ""),
                job_url=job.get("job_url", ""),
                description=(job.get("description", "") or "")[:16000], # truncating just in case
                date_posted=job.get("date_posted"),
                search_term=job.get("search_term", ""),
                is_remote=job.get("is_remote", False),
                applied_status=job.get("applied_status", False)
            )
            db_jobs.append(db_job)
        
        if db_jobs:
            session.add_all(db_jobs)
            session.commit()
            
            # Write the generated DB IDs back to the original dictionaries
            for job_dict, db_job in zip(jobs, db_jobs):
                job_dict["id"] = db_job.id
                
            logger.info(f"Successfully saved {len(db_jobs)} jobs to MySQL database for job_id: {search_job_id}")
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving jobs to database: {e}")
    finally:
        session.close()

def get_or_create_user(username: str):
    if not SessionLocal: return None
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            user = User(username=username)
            session.add(user)
            session.commit()
            session.refresh(user)
        return {"id": user.id, "username": user.username}
    except Exception as e:
        session.rollback()
        logger.error(f"Error in get_or_create_user: {e}")
        return None
    finally:
        session.close()

def create_search_session(user_id: int, job_id: str, search_params: str):
    if not SessionLocal: return
    session = SessionLocal()
    try:
        s_session = SearchSession(job_id=job_id, user_id=user_id, search_params=search_params)
        session.add(s_session)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating search session: {e}")
    finally:
        session.close()

def get_user_history(user_id: int):
    if not SessionLocal: return []
    session = SessionLocal()
    try:
        sessions = session.query(SearchSession).filter_by(user_id=user_id).order_by(SearchSession.created_at.desc()).all()
        return [{"job_id": s.job_id, "search_params": s.search_params, "created_at": s.created_at.isoformat()} for s in sessions]
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return []
    finally:
        session.close()

def get_jobs_for_session(job_id: str):
    if not SessionLocal: return []
    session = SessionLocal()
    try:
        jobs = session.query(JobResult).filter_by(job_id=job_id).all()
        result = []
        for j in jobs:
            result.append({
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "salary": j.salary_string or "N/A",
                "source": j.source,
                "score": j.match_score,
                "grade": j.match_grade,
                "date_posted": str(j.date_posted) if j.date_posted else "Today",
                "job_url": j.job_url,
                "description": j.description,
                "applied_status": j.applied_status
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        return []
    finally:
        session.close()

def update_job_applied_status(job_result_id: int, applied: bool):
    if not SessionLocal: return False
    session = SessionLocal()
    try:
        job = session.query(JobResult).filter_by(id=job_result_id).first()
        if job:
            job.applied_status = applied
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating applied status: {e}")
        return False
    finally:
        session.close()

def save_user_resume(user_id: int, filename: str, profile: dict):
    """Save the parsed resume info to the database."""
    if not SessionLocal:
        logger.error("Database not initialized. Cannot save resume.")
        return
    session = SessionLocal()
    try:
        import json
        resume = session.query(UserResume).filter_by(user_id=user_id).first()
        if not resume:
            resume = UserResume(user_id=user_id)
            session.add(resume)
        resume.filename = filename
        resume.skills = json.dumps(profile.get("skills", []))
        resume.suggested_titles = json.dumps(profile.get("suggested_titles", []))
        resume.experience_years = float(profile.get("experience_years", 1.5))
        resume.summary = profile.get("summary", "")
        resume.raw_text = profile.get("raw_text", "")
        resume.created_at = datetime.utcnow()
        session.commit()
        logger.info(f"Saved resume for user_id: {user_id}")
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving user resume: {e}")
    finally:
        session.close()

def get_user_resume(user_id: int):
    """Fetch the saved resume info for the user."""
    if not SessionLocal: return None
    session = SessionLocal()
    try:
        import json
        resume = session.query(UserResume).filter_by(user_id=user_id).first()
        if resume:
            return {
                "filename": resume.filename,
                "skills": json.loads(resume.skills or "[]"),
                "suggested_titles": json.loads(resume.suggested_titles or "[]"),
                "experience_years": resume.experience_years,
                "summary": resume.summary,
                "raw_text": resume.raw_text,
                "created_at": resume.created_at.isoformat()
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching user resume: {e}")
        return None
    finally:
        session.close()

def get_search_session(job_id: str):
    """Retrieve search session parameters by job_id."""
    if not SessionLocal: return None
    session = SessionLocal()
    try:
        s = session.query(SearchSession).filter_by(job_id=job_id).first()
        if s:
            return {
                "job_id": s.job_id,
                "user_id": s.user_id,
                "search_params": s.search_params,
                "created_at": s.created_at.isoformat()
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching search session: {e}")
        return None
    finally:
        session.close()

def delete_search_session_db(job_id: str) -> bool:
    if not SessionLocal: return False
    session = SessionLocal()
    try:
        # 1. Find the search session
        s = session.query(SearchSession).filter_by(job_id=job_id).first()
        if not s:
            return False
        
        # 2. Insert into deleted_search_sessions
        del_s = DeletedSearchSession(
            job_id=s.job_id,
            user_id=s.user_id,
            search_params=s.search_params,
            created_at=s.created_at
        )
        session.add(del_s)

        # 3. Find and move linked job results
        jobs = session.query(JobResult).filter_by(job_id=job_id).all()
        for j in jobs:
            del_j = DeletedJobResult(
                id=j.id,
                job_id=j.job_id,
                title=j.title,
                company=j.company,
                location=j.location,
                salary_string=j.salary_string,
                source=j.source,
                match_score=j.match_score,
                match_grade=j.match_grade,
                job_url=j.job_url,
                description=j.description,
                date_posted=j.date_posted,
                search_term=j.search_term,
                is_remote=j.is_remote,
                created_at=j.created_at,
                applied_status=j.applied_status
            )
            session.add(del_j)
            # Delete from active JobResult table
            session.delete(j)

        # 4. Delete active SearchSession
        session.delete(s)
        
        session.commit()
        logger.info(f"Moved search session {job_id} and its {len(jobs)} jobs to deleted tables.")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error in delete_search_session_db: {e}")
        return False
    finally:
        session.close()


