import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import structlog

logger = structlog.get_logger()

db_url = os.environ.get("DB_URL")
if not db_url:
    raise ValueError("DB_URL environment variable not set")

engine = create_engine(db_url, client_encoding='utf8', poolclass=NullPool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session():
    return SessionLocal()
