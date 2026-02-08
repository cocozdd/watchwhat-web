from dataclasses import dataclass, field
from typing import Set


@dataclass
class QueryConstraints:
    strict_types: Set[str] = field(default_factory=set)
    topic_tags: Set[str] = field(default_factory=set)
    language_preference: str = "zh_preferred"
    followup_on_sparse: bool = True
    friend_focus: bool = False


BOOK_KEYWORDS = ("小说", "书籍", "看书", "书", "阅读", "读书", "漫画")
TOPIC_KEYWORDS = {
    "mystery": ("推理", "悬疑", "侦探", "探案", "本格"),
    "sci-fi": ("科幻", "赛博", "太空", "宇宙", "未来"),
    "fantasy": ("奇幻", "魔法", "玄幻", "冒险"),
}
RELAX_TOPIC_KEYWORDS = ("都可", "都行", "都可以", "不限", "随意", "随便", "whatever", "any")
FRIEND_KEYWORDS = ("好友", "朋友", "豆友", "friend")


def parse_query_constraints(query: str) -> QueryConstraints:
    compact = (query or "").strip().lower()
    constraints = QueryConstraints()
    if any(keyword in compact for keyword in FRIEND_KEYWORDS):
        constraints.friend_focus = True
    if any(keyword in compact for keyword in BOOK_KEYWORDS):
        constraints.strict_types = {"book"}
    for topic_tag, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in compact for keyword in keywords):
            constraints.topic_tags.add(topic_tag)
    if any(keyword in compact for keyword in RELAX_TOPIC_KEYWORDS):
        constraints.topic_tags.clear()
    return constraints
