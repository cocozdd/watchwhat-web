from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.utcnow()


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("source", "username", name="uq_users_source_username"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(default="douban", index=True)
    username: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_synced_at: Optional[datetime] = Field(default=None)


class Item(SQLModel, table=True):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source", "subject_id", name="uq_items_source_subject_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(default="douban", index=True)
    subject_id: str = Field(index=True)
    type: str = Field(index=True)
    title: str
    year: Optional[int] = None
    douban_url: str
    meta_json: str = Field(default="{}")
    updated_at: datetime = Field(default_factory=utcnow)


class Interaction(SQLModel, table=True):
    __tablename__ = "interactions"
    __table_args__ = (UniqueConstraint("user_id", "item_id", name="uq_interactions_user_item"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    rating: Optional[float] = Field(default=None)
    interacted_at: Optional[datetime] = Field(default=None)
    comment: Optional[str] = Field(default=None)
    tags_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=utcnow)


class SyncJob(SQLModel, table=True):
    __tablename__ = "sync_jobs"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    source: str = Field(default="douban", index=True)
    status: str = Field(default="queued", index=True)
    done: int = Field(default=0)
    total: int = Field(default=0)
    message: str = Field(default="")
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = Field(default=None)


class RecommendSession(SQLModel, table=True):
    __tablename__ = "recommend_sessions"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    source: str = Field(default="douban", index=True)
    query: str
    status: str = Field(default="pending", index=True)
    needs_followup: bool = Field(default=False)
    followup_question: Optional[str] = Field(default=None)
    context_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RecommendResult(SQLModel, table=True):
    __tablename__ = "recommend_results"
    __table_args__ = (UniqueConstraint("session_id", "rank", name="uq_recommend_session_rank"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="recommend_sessions.id", index=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    rank: int = Field(index=True)
    score: float = Field(default=0.0)
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
