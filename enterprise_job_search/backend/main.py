from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.database import engine, Base
from api import auth_router

# Create database tables (in production, use Alembic migrations)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Enterprise Job Search Platform",
    description="AI-powered Job Search and Auto Apply API",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "job-search-api"}

app.include_router(auth_router.router)

