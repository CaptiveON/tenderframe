from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import timedelta
from app.database import get_db
from app.core.config import settings
from app.core.limits import rate_limit, client_ip
from app.schema.user import UserCreate, UserResponse
from app.schema.token import Token, LoginRequest
from app.services.user_service import user_service
from app.core.security import create_access_token


router = APIRouter(prefix="/user",tags=["authentication"])

@router.post("/anonymous", response_model=Token)
def create_anonymous_user(request: Request, db: Session = Depends(get_db)):
    # F2: throttle anonymous-token minting per IP
    rate_limit(f"anon:{client_ip(request)}", settings.ANON_CREATE_PER_HOUR, 3600)

    user = user_service.create_anonymous_user(db)

    access_token = create_access_token(
        data={"sub": user.id, "is_anonymous": "true"},
    )

    return Token(access_token=access_token, token_type="bearer")

@router.post("/registeration", response_model=UserResponse)
def create_new_user(
    user:UserCreate,
    request: Request,
    db:Session = Depends(get_db)
    ):
    # F2: throttle account creation per IP
    rate_limit(f"auth:{client_ip(request)}", settings.AUTH_RATE_PER_MIN, 60)

    return user_service.create_new_user(db, user)

@router.post("/login", response_model=Token)
def login(login_data: LoginRequest, request: Request, db:Session = Depends(get_db)):
    # F2: throttle login attempts per IP (brute-force protection)
    rate_limit(f"auth:{client_ip(request)}", settings.AUTH_RATE_PER_MIN, 60)

    user = user_service.authenticate_user(db, login_data)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=access_token_expires
    )
    
    return Token(access_token=access_token, token_type="bearer")