from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends

from backend.api.security import require
from backend.auth.permissions import CHAT_USE, FEEDBACK_READ, AuthenticatedUser
from backend.dependencies import get_feedback_repository, get_users
from backend.research.models import AnswerFeedback, FeedbackCreate

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=AnswerFeedback)
def give_feedback(payload: FeedbackCreate, user: AuthenticatedUser = Depends(require(CHAT_USE))) -> AnswerFeedback:
    """👍/👎 numa resposta do chat, com o motivo opcional. Guarda a pergunta, a resposta e as fontes para se
    perceber depois o que correu mal (e alimentar a avaliação do RAG)."""
    feedback = AnswerFeedback(
        feedback_id=str(uuid4()),
        user_id=user.user_id,
        created_at=datetime.now(UTC).isoformat(),
        **{**payload.model_dump(), "reason": payload.reason.strip()},
    )
    get_feedback_repository().add(feedback)
    return feedback


@router.get("", dependencies=[Depends(require(FEEDBACK_READ))])
def list_feedback(rating: int | None = None, limit: int = 200) -> dict:
    repo = get_feedback_repository()
    names = {u.user_id: u.display_name or u.username for u in get_users().list_users()}
    counts = repo.counts()
    return {
        "positive": counts.get(1, 0),
        "negative": counts.get(-1, 0),
        "items": [
            {**item.model_dump(), "user": names.get(item.user_id, "")}
            for item in repo.list_recent(limit=min(max(limit, 1), 1000), rating=rating)
        ],
    }
