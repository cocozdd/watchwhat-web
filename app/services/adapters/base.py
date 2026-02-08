from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence


@dataclass
class HistoryRecord:
    subject_id: str
    title: str
    type: str
    year: Optional[int]
    douban_url: str
    rating: Optional[float] = None
    interacted_at: Optional[datetime] = None
    comment: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class HistoryPage:
    records: List[HistoryRecord]
    next_cursor: Optional[int]


@dataclass
class CandidateItem:
    subject_id: str
    title: str
    type: str
    year: Optional[int]
    douban_url: str
    score: float = 0.0
    metadata: Dict[str, str] = field(default_factory=dict)


class SourceAdapter(ABC):
    @abstractmethod
    def fetch_history(
        self,
        username: str,
        cookie: Optional[str],
        page_cursor: int,
        media_type: str,
    ) -> HistoryPage:
        raise NotImplementedError

    @abstractmethod
    def fetch_candidate_pool(
        self,
        seed_items: Sequence[CandidateItem],
        cookie: Optional[str] = None,
    ) -> List[CandidateItem]:
        raise NotImplementedError
