import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import bcrypt
import logging

logger = logging.getLogger(__name__)

# Подключение к контейнеру database с правильными креденшиалами
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://admin_pg:supersecret@database:5432/tacacs_db"
)

logger.info(f"Connecting to database: {DATABASE_URL.split('@')[1]}")

try:
    engine = create_engine(DATABASE_URL)
    # Проверяем подключение
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database connection successful")
except Exception as e:
    logger.error(f"Database connection failed: {e}")
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    """Хеширование пароля с использованием bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')
