from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class MessageCreate(BaseModel):

    content: str
    session_id: Optional[str] = None
    mode: Optional[str] = None   # a domain label (e.g. 'vat') routes to the RAG pipeline

class MessageResponse(BaseModel):
    
    id: str
    role: str
    content: str
    created_at: datetime
    
    model_config = {
        "from_attributes": True
    }

class ChatSessionResponse(BaseModel):
    
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "from_attributes": True
    }
        
class ChatSessions(BaseModel):
    
    user_id: str
    chat_sessions: List[ChatSessionResponse]

class ChatHistory(BaseModel):
    
    session_id: str
    messages: List[MessageResponse]

class CitationOut(BaseModel):
    claim: str
    chunk_id: str
    verified: bool
    title: Optional[str] = None
    section_id: Optional[str] = None
    web_url: Optional[str] = None
    public_updated_at: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    user_message: MessageResponse
    bot_response: MessageResponse
    # RAG mode only: machine-readable citations for the future frontend
    citations: List[CitationOut] = []
    abstained: bool = False
    audit_id: Optional[int] = None
    