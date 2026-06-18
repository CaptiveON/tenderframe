from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.config import settings
from app.core.limits import rate_limit, consume_answer_quota
from app.models import User
from app.schema import MessageCreate, ChatResponse, MessageResponse, ChatSessionResponse, ChatSessions, ChatHistory
from app.services.chat_service import chat_service
from app.api.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/message", response_model=ChatResponse)
def send_message(
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # F1: per-user rate limit always; global daily spend cap on model-calling
    # (mode set) requests only — the echo path costs nothing.
    rate_limit(f"answer:{current_user.id}", settings.ANSWER_RATE_PER_MIN, 60)
    if message_data.mode:
        consume_answer_quota()

    return chat_service.process_message(db, current_user.id, message_data)

@router.get("/sessions", response_model=ChatSessions)
def get_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    
    return chat_service.get_chat_sessions(db, current_user.id)

@router.get("/chathistory/{session_id}",response_model=ChatHistory)
def get_chat_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    return chat_service.get_chat_history(db, current_user.id, session_id)
