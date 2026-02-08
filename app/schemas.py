from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    source: str = "douban"
    username: str
    cookie: Optional[str] = None
    force_full: bool = False
    sync_scope: Literal["auto", "book", "movie_tv", "all"] = "auto"


class SyncStartResponse(BaseModel):
    job_id: str
    status: str


class SyncCountSnapshot(BaseModel):
    movie_tv: int = 0
    book: int = 0
    total: int = 0


class SyncCountSummary(BaseModel):
    start: SyncCountSnapshot
    end: SyncCountSnapshot
    added: SyncCountSnapshot


class SyncPreviewItem(BaseModel):
    subject_id: str
    title: str
    type: str
    year: Optional[int] = None
    douban_url: str


class SyncStatusResponse(BaseModel):
    status: str
    done: int
    total: int
    message: str
    effective_username: Optional[str] = None
    counts: Optional[SyncCountSummary] = None
    added_preview: List[SyncPreviewItem] = Field(default_factory=list)


class FriendsSyncRequest(BaseModel):
    source: str = "douban"
    username: str
    cookie: Optional[str] = None
    force_full: bool = False
    sync_scope: Literal["auto", "book", "movie_tv", "all"] = "book"
    max_friends: int = Field(default=20, ge=1, le=200)


class FriendProfile(BaseModel):
    username: str
    display_name: str
    profile_url: str


class FriendsSyncResponse(BaseModel):
    status: str
    owner_username: str
    total_friends: int
    friend_usernames: List[str] = Field(default_factory=list)
    friend_profiles: List[FriendProfile] = Field(default_factory=list)
    job_ids: List[str] = Field(default_factory=list)


class LibraryItem(BaseModel):
    subject_id: str
    title: str
    type: str
    year: Optional[int] = None
    douban_url: str
    rating: Optional[float] = None
    interacted_at: Optional[datetime] = None


class LibraryResponse(BaseModel):
    source: str
    username: str
    total: int
    movie_tv_count: int
    book_count: int
    items: List[LibraryItem] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    subject_id: str
    title: str
    type: str
    year: Optional[int] = None
    douban_url: str
    score: float
    reason: str
    series_key: Optional[str] = None
    series_title_zh: Optional[str] = None
    is_series_representative: Optional[bool] = None


class RecommendRequest(BaseModel):
    source: str = "douban"
    username: str
    query: str
    top_k: int = Field(default=20, ge=1, le=100)
    allow_followup: bool = True
    friend_usernames: List[str] = Field(default_factory=list)
    friend_weights: Dict[str, float] = Field(default_factory=dict)


class AppliedConstraints(BaseModel):
    strict_types: List[str] = Field(default_factory=list)
    series_grouping: bool = True
    title_language: str = "zh_preferred"
    deduped_series_count: int = 0


class RecommendResponse(BaseModel):
    status: str
    followup_question: Optional[str] = None
    session_id: Optional[str] = None
    profile_summary: str = ""
    applied_constraints: Optional[AppliedConstraints] = None
    items: List[RecommendationItem] = Field(default_factory=list)


class FollowupRequest(BaseModel):
    session_id: str
    answer: str


class CookieCaptureStartRequest(BaseModel):
    source: str = "douban"


class CookieCaptureStatusResponse(BaseModel):
    job_id: str
    status: str
    message: str
    has_cookie: bool
