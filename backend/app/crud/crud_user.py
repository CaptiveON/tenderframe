from sqlalchemy.orm import Session
from app.models import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated = "auto")

def get_user_by_id(db:Session, user_id: str) -> User:
    
    return db.query(User).filter(User.id == user_id).first()

def get_user_by_email(db:Session, user_email:str) -> User:
    
    return db.query(User).filter(User.email == user_email).first()

def create_new_user(db: Session, user: User) -> User:

    db.add(user)
    db.commit()
    db.refresh(user) #Includes latest data like User ID
    
    return user

def create_anonymous_user(db: Session, user: User) -> User:
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user

# def get_user_password(db:Session):