import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Database URL configuration:
# Local development: SQLite database file "foodchoice.db"
# Production / Cloud: Environment variable DATABASE_URL (e.g., PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./foodchoice.db")

# PostgreSQL URL normalization (Render/Heroku often use "postgres://" instead of "postgresql://")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Engine connection arguments:
# "check_same_thread": False is required only for SQLite in multithreaded environments
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# Create the SQLAlchemy engine
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Session factory for database interactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all SQLAlchemy ORM models
Base = declarative_base()

def get_db():
    """FastAPI dependency to provide a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
