from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from app.models import UserCreate, UserUpdate, UserResponse, PasswordType
from app.database import hash_password
import logging

logger = logging.getLogger(__name__)

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user(self, user_id: int) -> Optional[UserResponse]:
        try:
            query = text("""
                SELECT id, username, password_hash, password_type, 
                       description, enabled, created_at, updated_at
                FROM tacacs.users 
                WHERE id = :user_id
            """)
            result = self.db.execute(query, {"user_id": user_id}).fetchone()
            
            if result:
                return UserResponse(
                    id=result.id,
                    username=result.username,
                    password_type=result.password_type,
                    description=result.description,
                    enabled=result.enabled,
                    created_at=result.created_at,
                    updated_at=result.updated_at
                )
            return None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    def get_user_by_username(self, username: str) -> Optional[UserResponse]:
        try:
            query = text("""
                SELECT id, username, password_hash, password_type, 
                       description, enabled, created_at, updated_at
                FROM tacacs.users 
                WHERE username = :username
            """)
            result = self.db.execute(query, {"username": username}).fetchone()
            
            if result:
                return UserResponse(
                    id=result.id,
                    username=result.username,
                    password_type=result.password_type,
                    description=result.description,
                    enabled=result.enabled,
                    created_at=result.created_at,
                    updated_at=result.updated_at
                )
            return None
        except Exception as e:
            logger.error(f"Error getting user by username {username}: {e}")
            return None

    def get_all_users(self) -> List[UserResponse]:
        try:
            query = text("""
                SELECT id, username, password_hash, password_type, 
                       description, enabled, created_at, updated_at
                FROM tacacs.users 
                ORDER BY id
            """)
            results = self.db.execute(query).fetchall()
            
            users = []
            for result in results:
                users.append(UserResponse(
                    id=result.id,
                    username=result.username,
                    password_type=result.password_type,
                    description=result.description,
                    enabled=result.enabled,
                    created_at=result.created_at,
                    updated_at=result.updated_at
                ))
            return users
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

    def create_user(self, user: UserCreate) -> Optional[UserResponse]:
        try:
            existing_user = self.get_user_by_username(user.username)
            if existing_user:
                return None

            password_hash = None
            if user.password_type == PasswordType.TEXT:
                password_hash = hash_password(user.password)
            elif user.password_type == PasswordType.QR:
                password_hash = user.password

            query = text("""
                INSERT INTO tacacs.users (username, password_hash, password_type, description, enabled)
                VALUES (:username, :password_hash, :password_type, :description, :enabled)
                RETURNING id, username, password_hash, password_type, 
                         description, enabled, created_at, updated_at
            """)
            
            result = self.db.execute(query, {
                "username": user.username,
                "password_hash": password_hash,
                "password_type": user.password_type.value,
                "description": user.description,
                "enabled": user.enabled
            }).fetchone()
            
            self.db.commit()
            
            return UserResponse(
                id=result.id,
                username=result.username,
                password_type=result.password_type,
                description=result.description,
                enabled=result.enabled,
                created_at=result.created_at,
                updated_at=result.updated_at
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating user {user.username}: {e}")
            return None

    def update_user(self, user_id: int, user_update: UserUpdate) -> Optional[UserResponse]:
        try:
            current_user = self.get_user(user_id)
            if not current_user:
                return None

            update_data = {}
            if user_update.username is not None:
                update_data["username"] = user_update.username
            if user_update.description is not None:
                update_data["description"] = user_update.description
            if user_update.enabled is not None:
                update_data["enabled"] = user_update.enabled
            
            if user_update.password is not None and user_update.password_type is not None:
                if user_update.password_type == PasswordType.TEXT:
                    update_data["password_hash"] = hash_password(user_update.password)
                    update_data["password_type"] = user_update.password_type.value
                elif user_update.password_type == PasswordType.QR:
                    update_data["password_hash"] = user_update.password
                    update_data["password_type"] = user_update.password_type.value

            if not update_data:
                return current_user

            set_clause = ", ".join([f"{key} = :{key}" for key in update_data.keys()])
            update_data["user_id"] = user_id

            query = text(f"""
                UPDATE tacacs.users 
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE id = :user_id
                RETURNING id, username, password_hash, password_type, 
                         description, enabled, created_at, updated_at
            """)
            
            result = self.db.execute(query, update_data).fetchone()
            self.db.commit()
            
            return UserResponse(
                id=result.id,
                username=result.username,
                password_type=result.password_type,
                description=result.description,
                enabled=result.enabled,
                created_at=result.created_at,
                updated_at=result.updated_at
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating user {user_id}: {e}")
            return None

    def delete_user(self, user_id: int) -> bool:
        try:
            query = text("DELETE FROM tacacs.users WHERE id = :user_id")
            result = self.db.execute(query, {"user_id": user_id})
            self.db.commit()
            return result.rowcount > 0
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting user {user_id}: {e}")
            return False
