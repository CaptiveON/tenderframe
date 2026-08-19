from app.database import Base, engine
from .user import User
from .chat import ChatSession, Message

# Auto-create our tables on startup if missing. create_all is idempotent: it only
# creates tables that don't already exist, so it's a safe no-op when they're present.
#
# Do NOT add drop_all here: this DB is shared, and `users` has an inbound foreign key
# from the externally-owned `query_audit_logs` table, so DROP TABLE users fails — and
# DROP ... CASCADE would destroy a teammate's RAG data. Never drop on startup.
# Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

__all__ = ["User","ChatSession","Message"]
