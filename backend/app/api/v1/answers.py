from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.exceptions.base import AppException
from app.models import User
from app.models.rag import AuditLog
from app.rag.audit import render_audit
from fastapi import status

router = APIRouter(prefix="/answers", tags=["audit"])


class AuditNotFound(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Audit record not found."


@router.get("/{audit_id}/audit")
def get_answer_audit(
    audit_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(AuditLog, audit_id)
    # owner-only: an audit trail contains the user's own Q&A
    if row is None or row.user_id != current_user.id:
        raise AuditNotFound()
    return render_audit(db, row)
