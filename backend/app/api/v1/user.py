from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import timedelta
from app.database import get_db
from app.core.config import settings
from app.schema.user import UserCreate, UserResponse
from app.schema.token import Token, LoginRequest
from app.services.user_service import user_service
from app.core.security import create_access_token


router = APIRouter(prefix="/user",tags=["authentication"])

@router.post("/anonymous", response_model=Token)
def create_anonymous_user(db: Session = Depends(get_db)):
    
    user = user_service.create_anonymous_user(db)
    
    access_token = create_access_token(
        data={"sub": user.id, "is_anonymous": "true"},
    )
    
    return Token(access_token=access_token, token_type="bearer")

@router.post("/registeration", response_model=UserResponse)
def create_new_user(
    user:UserCreate,
    db:Session = Depends(get_db)
    ):
    
    return user_service.create_new_user(db, user)

@router.post("/login", response_model=Token)
def login(login_data: LoginRequest, db:Session = Depends(get_db)):
    
    user = user_service.authenticate_user(db, login_data)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=access_token_expires
    )
    
    return Token(access_token=access_token, token_type="bearer")