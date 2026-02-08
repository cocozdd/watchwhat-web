from fastapi import APIRouter, HTTPException

from app.schemas import FollowupRequest, RecommendRequest, RecommendResponse
from app.services.douban_username import normalize_douban_username
from app.services.recommendation_engine import RecommendationEngine

router = APIRouter(tags=["recommend"])
engine = RecommendationEngine()


@router.post("/recommend", response_model=RecommendResponse)
def recommend(request: RecommendRequest) -> RecommendResponse:
    if request.source != "douban":
        raise HTTPException(status_code=400, detail="Only douban source is supported in v1")

    normalized_username = normalize_douban_username(request.username)
    if not normalized_username:
        raise HTTPException(
            status_code=400,
            detail="Invalid Douban username. Please provide a username or profile URL with /people/<username>/.",
        )

    try:
        return engine.recommend(
            source=request.source,
            username=normalized_username,
            query=request.query,
            top_k=request.top_k,
            allow_followup=request.allow_followup,
            friend_usernames=request.friend_usernames,
            friend_weights=request.friend_weights,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recommend/followup", response_model=RecommendResponse)
def recommend_followup(request: FollowupRequest) -> RecommendResponse:
    try:
        return engine.answer_followup(request.session_id, request.answer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
