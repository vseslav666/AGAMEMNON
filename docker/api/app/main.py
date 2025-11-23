from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List

from app.database import get_db
from app.models import UserCreate, UserUpdate, UserResponse, UserListResponse, PasswordType
from app.repositories.user_repository import UserRepository

app = FastAPI(
    title="TACACS User Management API",
    description="API для управления пользователями TACACS",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "TACACS User Management API"}

@app.post("/users/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    user_repo = UserRepository(db)
    created_user = user_repo.create_user(user)
    
    if not created_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username already exists or creation failed"
        )
    
    return created_user

@app.get("/users/", response_model=UserListResponse)
async def get_all_users(db: Session = Depends(get_db)):
    user_repo = UserRepository(db)
    users = user_repo.get_all_users()
    
    return UserListResponse(users=users, total=len(users))

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user_repo = UserRepository(db)
    user = user_repo.get_user(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user

@app.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    user_repo = UserRepository(db)
    updated_user = user_repo.update_user(user_id, user_update)
    
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return updated_user

@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user_repo = UserRepository(db)
    success = user_repo.delete_user(user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

@app.post("/generate-config/")
async def generate_config():
    """
    Заглушка для генерации конфигурации
    TODO: Реализовать позже
    """
    return {
        "message": "Configuration generation endpoint - to be implemented",
        "status": "not_implemented"
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        # Исправленная версия с text()
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )
