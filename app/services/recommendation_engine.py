import json
import math
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_engine
from app.models import Interaction, Item, RecommendSession, User
from app.schemas import AppliedConstraints, RecommendResponse, RecommendationItem
from app.services import adapters
from app.services.adapters.base import CandidateItem
from app.services.douban_username import normalize_douban_username
from app.services.llm_deepseek import DeepSeekClient
from app.services.query_constraints import QueryConstraints, parse_query_constraints
from app.services.series_normalizer import build_series_identity

FALLBACK_CANDIDATE_CATALOG = [
    {
        "subject_id": "fallback-movie-parasite",
        "title": "Parasite",
        "type": "movie",
        "year": 2019,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Parasite",
        "score": 0.9,
    },
    {
        "subject_id": "fallback-movie-dune-part-two",
        "title": "Dune: Part Two",
        "type": "movie",
        "year": 2024,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Dune%20Part%20Two",
        "score": 0.88,
    },
    {
        "subject_id": "fallback-movie-oppenheimer",
        "title": "Oppenheimer",
        "type": "movie",
        "year": 2023,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Oppenheimer",
        "score": 0.87,
    },
    {
        "subject_id": "fallback-movie-past-lives",
        "title": "Past Lives",
        "type": "movie",
        "year": 2023,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Past%20Lives",
        "score": 0.84,
    },
    {
        "subject_id": "fallback-movie-green-book",
        "title": "Green Book",
        "type": "movie",
        "year": 2018,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Green%20Book",
        "score": 0.82,
    },
    {
        "subject_id": "fallback-tv-the-bear",
        "title": "The Bear",
        "type": "tv",
        "year": 2022,
        "douban_url": "https://www.douban.com/search?cat=1002&q=The%20Bear",
        "score": 0.87,
    },
    {
        "subject_id": "fallback-tv-arcane",
        "title": "Arcane",
        "type": "tv",
        "year": 2021,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Arcane",
        "score": 0.86,
    },
    {
        "subject_id": "fallback-tv-succession",
        "title": "Succession",
        "type": "tv",
        "year": 2018,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Succession",
        "score": 0.85,
    },
    {
        "subject_id": "fallback-tv-shogun",
        "title": "Shogun",
        "type": "tv",
        "year": 2024,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Shogun",
        "score": 0.86,
    },
    {
        "subject_id": "fallback-tv-severance",
        "title": "Severance",
        "type": "tv",
        "year": 2022,
        "douban_url": "https://www.douban.com/search?cat=1002&q=Severance",
        "score": 0.84,
    },
    {
        "subject_id": "fallback-book-xianyi-x",
        "title": "嫌疑人X的献身",
        "display_title_zh": "嫌疑人X的献身",
        "type": "book",
        "year": 2005,
        "douban_url": "https://book.douban.com/subject/2307791/",
        "score": 0.95,
        "tags": ["mystery"],
    },
    {
        "subject_id": "fallback-book-byh",
        "title": "白夜行",
        "display_title_zh": "白夜行",
        "type": "book",
        "year": 1999,
        "douban_url": "https://book.douban.com/subject/3259440/",
        "score": 0.94,
        "tags": ["mystery"],
    },
    {
        "subject_id": "fallback-book-ew",
        "title": "恶意",
        "display_title_zh": "恶意",
        "type": "book",
        "year": 1996,
        "douban_url": "https://book.douban.com/subject/1438652/",
        "score": 0.92,
        "tags": ["mystery"],
    },
    {
        "subject_id": "fallback-book-three-body",
        "title": "三体",
        "display_title_zh": "三体",
        "type": "book",
        "year": 2008,
        "douban_url": "https://book.douban.com/subject/2567698/",
        "score": 0.89,
        "tags": ["sci-fi"],
    },
    {
        "subject_id": "fallback-book-liulangdiqiu",
        "title": "流浪地球",
        "display_title_zh": "流浪地球",
        "type": "book",
        "year": 2000,
        "douban_url": "https://book.douban.com/subject/26292448/",
        "score": 0.86,
        "tags": ["sci-fi"],
    },
]


class RecommendationEngine:
    def __init__(self):
        self.llm_client = DeepSeekClient()

    def recommend(
        self,
        source: str,
        username: str,
        query: str,
        top_k: int,
        allow_followup: bool,
        friend_usernames: Optional[List[str]] = None,
        friend_weights: Optional[Dict[str, float]] = None,
    ) -> RecommendResponse:
        constraints = parse_query_constraints(query)
        normalized_friend_usernames = self._normalize_friend_usernames(friend_usernames, username)
        normalized_friend_weights = self._normalize_friend_weights(
            friend_usernames=normalized_friend_usernames,
            raw_friend_weights=friend_weights,
        )
        with Session(get_engine()) as session:
            user = self._find_user(session, source, username)
            if user is None:
                raise ValueError("User has no synced data. Please sync first.")

            history = self._load_history(session, user.id)
            if not history:
                raise ValueError("No history found for this user. Please sync first.")

            profile_summary = self._build_profile_summary(history)
            seen_subject_ids = {item.subject_id for _, item in history}
            seen_series_keys = self._history_series_keys(history)

            adapter = adapters.get_source_adapter(source)
            seeds = self._build_seed_items(history)
            try:
                external_candidates = adapter.fetch_candidate_pool(seeds)
            except Exception:
                external_candidates = []
            friend_candidates, loaded_friend_usernames, contributing_friend_usernames = self._build_friend_candidates(
                session=session,
                source=source,
                friend_usernames=normalized_friend_usernames,
                friend_weights=normalized_friend_weights,
                seen_subject_ids=seen_subject_ids,
                constraints=constraints,
            )
            selected_friend_count = len(normalized_friend_usernames)
            loaded_friend_count = len(loaded_friend_usernames)
            contributing_friend_count = len(contributing_friend_usernames)
            if selected_friend_count > 0:
                profile_summary = (
                    f"{profile_summary}；好友已加载 {loaded_friend_count}/{selected_friend_count} 位"
                )
                if loaded_friend_count < selected_friend_count:
                    profile_summary = (
                        f"{profile_summary}（部分好友尚未同步成功，可能被豆瓣风控拦截）"
                    )
            if friend_candidates:
                profile_summary = (
                    f"{profile_summary}；好友候选 {len(friend_candidates)} 条（来自 {contributing_friend_count} 位好友）"
                )

            deduped_series_count = 0
            friend_focus_active = bool(constraints.friend_focus and normalized_friend_usernames)
            merged_candidates = friend_candidates if friend_focus_active else (friend_candidates + external_candidates)
            if friend_focus_active:
                profile_summary = f"{profile_summary}；已启用好友优先候选"
            candidates = self._annotate_candidates(merged_candidates, constraints)
            candidates, reduced = self._dedupe_and_filter_unseen(
                candidates=candidates,
                seen_subject_ids=seen_subject_ids,
                seen_series_keys=seen_series_keys,
                constraints=constraints,
            )
            deduped_series_count += reduced

            using_fallback_catalog = False
            if not candidates:
                fallback_candidates = self._fallback_candidates(
                    query=query,
                    history=history,
                    seen_subject_ids=seen_subject_ids,
                    constraints=constraints,
                )
                fallback_candidates = self._annotate_candidates(fallback_candidates, constraints)
                fallback_candidates, reduced = self._dedupe_and_filter_unseen(
                    candidates=fallback_candidates,
                    seen_subject_ids=seen_subject_ids,
                    seen_series_keys=seen_series_keys,
                    constraints=constraints,
                )
                candidates = fallback_candidates
                deduped_series_count += reduced
                using_fallback_catalog = True

            applied_constraints = self._build_applied_constraints(
                constraints=constraints,
                deduped_series_count=deduped_series_count,
            )

            if not candidates:
                if allow_followup and self._needs_sparse_followup(constraints, top_k=top_k, item_count=0):
                    return self._build_followup_response(
                        session=session,
                        user_id=user.id,
                        source=source,
                        query=query,
                        top_k=top_k,
                        friend_usernames=normalized_friend_usernames,
                        friend_weights=normalized_friend_weights,
                        profile_summary=profile_summary,
                        applied_constraints=applied_constraints,
                        question="当前书籍候选不足，需补充题材/年代偏好。",
                    )
                if constraints.strict_types:
                    return RecommendResponse(
                        status="ok",
                        profile_summary=f"{profile_summary}；当前条件下暂无未读候选，可放宽题材关键词后重试。",
                        applied_constraints=applied_constraints,
                        items=[],
                    )
                raise ValueError(
                    "No candidate items available. Douban may be blocking candidate fetch. "
                    "Please recapture cookie and sync again."
                )

            if using_fallback_catalog:
                profile_summary = f"{profile_summary}; 候选来源: 本地回退库"

            if allow_followup and self._needs_followup(query, candidates):
                return self._build_followup_response(
                    session=session,
                    user_id=user.id,
                    source=source,
                    query=query,
                    top_k=top_k,
                    friend_usernames=normalized_friend_usernames,
                    friend_weights=normalized_friend_weights,
                    profile_summary=profile_summary,
                    applied_constraints=applied_constraints,
                    question="你更偏向电影、剧集还是书籍？以及时间范围（如近5年）？",
                )

            ranking = self._rank_candidates(
                query=query,
                profile_summary=profile_summary,
                candidates=candidates,
                allow_followup=allow_followup,
                constraints=constraints,
                use_llm=not friend_focus_active,
            )
            ranking = self._post_validate_ranked_items(ranking, constraints)

            if allow_followup and self._needs_sparse_followup(
                constraints=constraints,
                top_k=top_k,
                item_count=len(ranking),
            ):
                return self._build_followup_response(
                    session=session,
                    user_id=user.id,
                    source=source,
                    query=query,
                    top_k=top_k,
                    friend_usernames=normalized_friend_usernames,
                    friend_weights=normalized_friend_weights,
                    profile_summary=profile_summary,
                    applied_constraints=applied_constraints,
                    question="当前书籍候选不足，需补充题材/年代偏好。",
                )

            response_items = self._to_response_items(ranking, top_k)
            return RecommendResponse(
                status="ok",
                profile_summary=profile_summary,
                applied_constraints=applied_constraints,
                items=response_items,
            )

    def answer_followup(self, session_id: str, answer: str) -> RecommendResponse:
        with Session(get_engine()) as session:
            followup = session.get(RecommendSession, session_id)
            if followup is None:
                raise ValueError("Follow-up session not found")
            if not followup.needs_followup:
                raise ValueError("Follow-up session is no longer active")

            context = json.loads(followup.context_json)
            merged_query = f"{followup.query}\n补充偏好: {answer}"
            followup.needs_followup = False
            followup.status = "completed"
            followup.updated_at = datetime.utcnow()
            session.add(followup)
            session.commit()

        return self.recommend(
            source=context["source"],
            username=context["username"],
            query=merged_query,
            top_k=int(context.get("top_k", 20)),
            allow_followup=False,
            friend_usernames=context.get("friend_usernames", []),
            friend_weights=context.get("friend_weights", {}),
        )

    def _build_followup_response(
        self,
        session: Session,
        user_id: int,
        source: str,
        query: str,
        top_k: int,
        friend_usernames: Optional[List[str]],
        friend_weights: Optional[Dict[str, float]],
        profile_summary: str,
        applied_constraints: AppliedConstraints,
        question: str,
    ) -> RecommendResponse:
        followup_session = self._create_followup_session(
            session=session,
            user_id=user_id,
            source=source,
            query=query,
            top_k=top_k,
            friend_usernames=friend_usernames,
            friend_weights=friend_weights,
        )
        return RecommendResponse(
            status="need_followup",
            followup_question=question,
            session_id=followup_session.id,
            profile_summary=profile_summary,
            applied_constraints=applied_constraints,
            items=[],
        )

    def _find_user(self, session: Session, source: str, username: str) -> Optional[User]:
        statement = select(User).where(User.source == source, User.username == username)
        return session.exec(statement).first()

    def _normalize_friend_usernames(self, friend_usernames: Optional[List[str]], username: str) -> List[str]:
        if not friend_usernames:
            return []
        normalized_owner = normalize_douban_username(username) or username
        owner_lower = normalized_owner.lower()
        normalized: List[str] = []
        seen = set()
        for value in friend_usernames:
            compact = (value or "").strip()
            if not compact:
                continue
            parsed = normalize_douban_username(compact)
            if parsed and parsed != "__mine__":
                compact = parsed
            if compact.lower() == owner_lower:
                continue
            key = compact.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(compact)
        return normalized

    def _normalize_friend_weights(
        self,
        friend_usernames: Sequence[str],
        raw_friend_weights: Optional[Dict[str, float]],
    ) -> Dict[str, float]:
        if not friend_usernames:
            return {}
        weights = {name.lower(): 1.0 for name in friend_usernames}
        if not raw_friend_weights:
            return weights

        for raw_name, raw_weight in raw_friend_weights.items():
            compact = (raw_name or "").strip()
            if not compact:
                continue
            parsed = normalize_douban_username(compact)
            if parsed and parsed != "__mine__":
                compact = parsed

            normalized_key = compact.lower()
            if normalized_key not in weights:
                continue

            try:
                value = float(raw_weight)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            # Keep user-editable range stable and predictable in UI/API.
            weights[normalized_key] = min(5.0, max(0.1, value))
        return weights

    def _build_friend_candidates(
        self,
        session: Session,
        source: str,
        friend_usernames: Sequence[str],
        friend_weights: Dict[str, float],
        seen_subject_ids: Set[str],
        constraints: QueryConstraints,
    ) -> Tuple[List[CandidateItem], Set[str], Set[str]]:
        if not friend_usernames:
            return [], set(), set()

        friend_stmt = select(User).where(User.source == source, User.username.in_(list(friend_usernames)))
        friend_users = session.exec(friend_stmt).all()
        if not friend_users:
            lowered = {name.lower() for name in friend_usernames if name}
            if not lowered:
                return [], set(), set()
            ci_stmt = select(User).where(User.source == source, func.lower(User.username).in_(list(lowered)))
            friend_users = session.exec(ci_stmt).all()
            if not friend_users:
                return [], set(), set()

        aggregated: Dict[str, dict] = {}
        loaded_friend_usernames: Set[str] = set()
        contributing_friend_usernames: Set[str] = set()
        for friend_user in friend_users:
            username_key = friend_user.username.lower()
            user_weight = friend_weights.get(username_key, 1.0)
            if user_weight <= 0:
                continue
            rows = self._load_history(session, friend_user.id)
            if rows:
                loaded_friend_usernames.add(friend_user.username.lower())
            for interaction, item in rows:
                if constraints.strict_types and item.type not in constraints.strict_types:
                    continue
                if item.subject_id in seen_subject_ids:
                    continue
                if interaction.rating is None or interaction.rating < 7:
                    continue
                contributing_friend_usernames.add(friend_user.username.lower())

                bucket = aggregated.setdefault(
                    item.subject_id,
                    {
                        "item": item,
                        "ratings": [],
                        "weighted_rating_sum": 0.0,
                        "weight_sum": 0.0,
                        "usernames": set(),
                        "latest_interacted_at": None,
                        "comment_chars": 0,
                    },
                )
                bucket["ratings"].append(float(interaction.rating))
                bucket["weighted_rating_sum"] += float(interaction.rating) * user_weight
                bucket["weight_sum"] += user_weight
                bucket["usernames"].add(friend_user.username)
                if interaction.interacted_at is not None:
                    latest_dt = bucket.get("latest_interacted_at")
                    if latest_dt is None or interaction.interacted_at > latest_dt:
                        bucket["latest_interacted_at"] = interaction.interacted_at
                if interaction.comment:
                    bucket["comment_chars"] += len(interaction.comment.strip())

        candidates: List[CandidateItem] = []
        for subject_id, bucket in aggregated.items():
            item: Item = bucket["item"]
            usernames = bucket["usernames"]
            weighted_rating_sum = float(bucket.get("weighted_rating_sum", 0.0) or 0.0)
            weight_sum = float(bucket.get("weight_sum", 0.0) or 0.0)
            latest_interacted_at = bucket.get("latest_interacted_at")
            comment_chars = int(bucket.get("comment_chars", 0) or 0)
            friend_count = len(usernames)
            if friend_count == 0 or weight_sum <= 0.0:
                continue
            avg_rating = weighted_rating_sum / weight_sum
            social_boost = min(weight_sum / 3.0, 1.0)
            comment_boost = min(comment_chars / 160.0, 1.0) * 0.06
            recency_boost = 0.0
            latest_ts = 0.0
            if latest_interacted_at is not None:
                latest_ts = max(latest_interacted_at.timestamp(), 0.0)
                days_since = max(0.0, (datetime.utcnow() - latest_interacted_at).total_seconds() / 86400.0)
                recency_boost = max(0.0, 1.0 - min(days_since, 3650.0) / 3650.0) * 0.05

            score = min(0.99, 0.38 + 0.40 * (avg_rating / 10.0) + 0.17 * social_boost + comment_boost + recency_boost)

            candidates.append(
                CandidateItem(
                    subject_id=subject_id,
                    title=item.title,
                    type=item.type,
                    year=item.year,
                    douban_url=item.douban_url,
                    score=round(score, 4),
                    metadata={
                        "friend_count": str(friend_count),
                        "friend_avg_rating": f"{avg_rating:.2f}",
                        "friend_users": ",".join(sorted(usernames)[:5]),
                        "friend_weight_sum": f"{weight_sum:.3f}",
                        "friend_weight_avg": f"{(weight_sum / friend_count):.3f}",
                        "friend_latest_ts": f"{latest_ts:.3f}",
                        "friend_latest_date": latest_interacted_at.isoformat() if latest_interacted_at else "",
                        "friend_comment_chars": str(comment_chars),
                    },
                )
            )

        candidates.sort(
            key=lambda candidate: (
                candidate.score,
                self._candidate_friend_latest_ts(candidate),
                candidate.year or 0,
            ),
            reverse=True,
        )
        return candidates, loaded_friend_usernames, contributing_friend_usernames

    def _load_history(self, session: Session, user_id: int) -> List[Tuple[Interaction, Item]]:
        statement = (
            select(Interaction, Item)
            .join(Item, Interaction.item_id == Item.id)
            .where(Interaction.user_id == user_id)
        )
        rows = session.exec(statement).all()
        return list(rows)

    def _history_series_keys(self, history: Sequence[Tuple[Interaction, Item]]) -> Set[str]:
        keys: Set[str] = set()
        for _, item in history:
            identity = build_series_identity(item.title, item.type)
            keys.add(identity.series_key)
        return keys

    def _build_profile_summary(self, history: Sequence[Tuple[Interaction, Item]]) -> str:
        by_series: Dict[str, Tuple[Interaction, Item, str]] = {}
        for interaction, item in history:
            identity = build_series_identity(item.title, item.type)
            current = by_series.get(identity.series_key)
            if current is None:
                by_series[identity.series_key] = (interaction, item, identity.series_display_title_zh)
                continue
            current_interaction = current[0]
            current_score = current_interaction.rating if current_interaction.rating is not None else -1.0
            next_score = interaction.rating if interaction.rating is not None else -1.0
            if next_score > current_score:
                by_series[identity.series_key] = (interaction, item, identity.series_display_title_zh)

        by_type: Dict[str, List[float]] = {"movie": [], "tv": [], "book": []}
        for interaction, item, _ in by_series.values():
            if interaction.rating is not None:
                by_type.setdefault(item.type, []).append(interaction.rating)

        liked_titles: List[str] = []
        sorted_representatives = sorted(
            by_series.values(),
            key=lambda row: (row[0].rating if row[0].rating is not None else -1.0),
            reverse=True,
        )
        for interaction, _, display_title in sorted_representatives:
            if interaction.rating is None or interaction.rating < 8:
                continue
            if display_title in liked_titles:
                continue
            liked_titles.append(display_title)
            if len(liked_titles) >= 5:
                break

        display_type = {"movie": "电影", "tv": "剧集", "book": "书籍"}
        parts: List[str] = []
        for item_type in ("movie", "tv", "book"):
            scores = by_type.get(item_type, [])
            if scores:
                avg = sum(scores) / len(scores)
                parts.append(f"{display_type.get(item_type, item_type)}平均评分 {avg:.1f}")

        if liked_titles:
            parts.append("高分样本: " + "、".join(liked_titles))

        return "；".join(parts) if parts else "画像信号较少"

    def _build_seed_items(self, history: Sequence[Tuple[Interaction, Item]]) -> List[CandidateItem]:
        sorted_rows = sorted(
            history,
            key=lambda row: row[0].rating if row[0].rating is not None else 0.0,
            reverse=True,
        )
        seeds: List[CandidateItem] = []
        seen_series: Set[str] = set()
        for interaction, item in sorted_rows:
            identity = build_series_identity(item.title, item.type)
            if identity.series_key in seen_series:
                continue
            seen_series.add(identity.series_key)
            score = (interaction.rating or 6.0) / 10.0
            metadata = {
                "series_key": identity.series_key,
                "series_title_zh": identity.series_display_title_zh,
                "is_series_variant": "true" if identity.is_variant else "false",
            }
            seeds.append(
                CandidateItem(
                    subject_id=item.subject_id,
                    title=identity.series_display_title_zh,
                    type=item.type,
                    year=item.year,
                    douban_url=item.douban_url,
                    score=score,
                    metadata=metadata,
                )
            )
            if len(seeds) >= 10:
                break
        return seeds

    def _annotate_candidates(
        self,
        candidates: Sequence[CandidateItem],
        constraints: QueryConstraints,
    ) -> List[CandidateItem]:
        annotated: List[CandidateItem] = []
        for candidate in candidates:
            identity = build_series_identity(candidate.title, candidate.type)
            metadata = dict(candidate.metadata or {})
            preferred_zh_title = metadata.get("display_title_zh") or identity.series_display_title_zh
            display_title = candidate.title
            if constraints.language_preference == "zh_preferred":
                display_title = (
                    metadata.get("display_title_zh")
                    or metadata.get("series_title_zh")
                    or preferred_zh_title
                    or display_title
                )
            metadata["series_key"] = identity.series_key
            metadata["series_title_zh"] = preferred_zh_title
            metadata["is_series_variant"] = "true" if identity.is_variant else "false"

            annotated.append(
                CandidateItem(
                    subject_id=candidate.subject_id,
                    title=display_title,
                    type=candidate.type,
                    year=candidate.year,
                    douban_url=candidate.douban_url,
                    score=candidate.score,
                    metadata=metadata,
                )
            )
        return annotated

    def _dedupe_and_filter_unseen(
        self,
        candidates: Sequence[CandidateItem],
        seen_subject_ids: Set[str],
        seen_series_keys: Set[str],
        constraints: QueryConstraints,
    ) -> Tuple[List[CandidateItem], int]:
        deduped: List[CandidateItem] = []
        emitted_subjects: Set[str] = set()
        emitted_series = set(seen_series_keys)
        deduped_series_count = 0

        sorted_candidates = sorted(
            candidates,
            key=lambda candidate: (
                candidate.score,
                self._candidate_friend_latest_ts(candidate),
                candidate.year or 0,
            ),
            reverse=True,
        )
        for candidate in sorted_candidates:
            if constraints.strict_types and candidate.type not in constraints.strict_types:
                continue
            if candidate.subject_id in seen_subject_ids:
                continue
            if candidate.subject_id in emitted_subjects:
                continue
            series_key = self._candidate_series_key(candidate)
            if series_key in emitted_series:
                deduped_series_count += 1
                continue
            emitted_subjects.add(candidate.subject_id)
            emitted_series.add(series_key)
            deduped.append(candidate)
        return deduped, deduped_series_count

    def _needs_followup(self, query: str, candidates: Sequence[CandidateItem]) -> bool:
        del candidates
        compact = query.strip().lower()
        if compact in {"随便", "whatever", "any"}:
            return True
        if len(compact) <= 2:
            return True
        return False

    def _needs_sparse_followup(self, constraints: QueryConstraints, top_k: int, item_count: int) -> bool:
        if not constraints.followup_on_sparse:
            return False
        if "book" not in constraints.strict_types:
            return False
        threshold = min(3, max(1, top_k))
        return item_count < threshold

    def _create_followup_session(
        self,
        session: Session,
        user_id: int,
        source: str,
        query: str,
        top_k: int,
        friend_usernames: Optional[List[str]] = None,
        friend_weights: Optional[Dict[str, float]] = None,
    ) -> RecommendSession:
        followup = RecommendSession(
            user_id=user_id,
            source=source,
            query=query,
            status="need_followup",
            needs_followup=True,
            followup_question="请补充类型和时间偏好",
            context_json=json.dumps(
                {
                    "source": source,
                    "username": self._username_by_id(session, user_id),
                    "top_k": top_k,
                    "friend_usernames": friend_usernames or [],
                    "friend_weights": friend_weights or {},
                }
            ),
        )
        session.add(followup)
        session.commit()
        session.refresh(followup)
        return followup

    def _username_by_id(self, session: Session, user_id: int) -> str:
        user = session.get(User, user_id)
        return user.username if user else ""

    def _rank_candidates(
        self,
        query: str,
        profile_summary: str,
        candidates: List[CandidateItem],
        allow_followup: bool,
        constraints: QueryConstraints,
        use_llm: bool,
    ) -> List[RecommendationItem]:
        llm_ranked = None
        if use_llm and self.llm_client.configured():
            try:
                llm_ranked = self.llm_client.recommend(
                    query=query,
                    profile_summary=profile_summary,
                    candidates=candidates,
                    allow_followup=allow_followup,
                    strict_types=constraints.strict_types,
                    language_preference=constraints.language_preference,
                )
            except Exception:
                llm_ranked = None

        if llm_ranked is not None and llm_ranked.ranked:
            candidate_map = {candidate.subject_id: candidate for candidate in candidates}
            ranked_items: List[RecommendationItem] = []
            used_subjects: Set[str] = set()
            used_series: Set[str] = set()

            for choice in llm_ranked.ranked:
                candidate = candidate_map.get(choice.subject_id)
                if candidate is None:
                    continue
                if constraints.strict_types and candidate.type not in constraints.strict_types:
                    continue
                if candidate.subject_id in used_subjects:
                    continue
                series_key = self._candidate_series_key(candidate)
                if series_key in used_series:
                    continue
                used_subjects.add(candidate.subject_id)
                used_series.add(series_key)
                ranked_items.append(self._candidate_to_response(candidate, score=float(choice.score), reason=choice.reason))

            for candidate in candidates:
                if constraints.strict_types and candidate.type not in constraints.strict_types:
                    continue
                if candidate.subject_id in used_subjects:
                    continue
                series_key = self._candidate_series_key(candidate)
                if series_key in used_series:
                    continue
                used_subjects.add(candidate.subject_id)
                used_series.add(series_key)
                ranked_items.append(
                    self._candidate_to_response(
                        candidate,
                        score=float(candidate.score),
                        reason=self._friend_reason(candidate) or "与历史高分偏好相似",
                    )
                )
            return ranked_items

        now_year = datetime.utcnow().year
        movie_hint = "电影" in query
        tv_hint = "剧" in query or "电视剧" in query
        book_hint = "书" in query or "阅读" in query
        recent_hint = "近" in query or "最近" in query

        scored = []
        for candidate in candidates:
            if constraints.strict_types and candidate.type not in constraints.strict_types:
                continue
            score = candidate.score
            if recent_hint and candidate.year and candidate.year >= now_year - 5:
                score += 0.25
            if movie_hint and candidate.type == "movie":
                score += 0.2
            if tv_hint and candidate.type == "tv":
                score += 0.2
            if book_hint and candidate.type == "book":
                score += 0.2
            scored.append((score, candidate))

        scored.sort(
            key=lambda row: (
                row[0],
                self._candidate_friend_latest_ts(row[1]),
                row[1].year or 0,
            ),
            reverse=True,
        )

        result: List[RecommendationItem] = []
        used_series: Set[str] = set()
        for score, candidate in scored:
            series_key = self._candidate_series_key(candidate)
            if series_key in used_series:
                continue
            used_series.add(series_key)
            reason_parts = [self._friend_reason(candidate) or "匹配你的历史高分偏好"]
            if candidate.year:
                reason_parts.append(f"年份 {candidate.year}")
            if recent_hint and candidate.year and candidate.year >= now_year - 5:
                reason_parts.append("符合近年偏好")
            result.append(
                self._candidate_to_response(
                    candidate,
                    score=round(float(score), 4),
                    reason="，".join(reason_parts),
                )
            )
        return result

    def _post_validate_ranked_items(
        self,
        ranked_items: Sequence[RecommendationItem],
        constraints: QueryConstraints,
    ) -> List[RecommendationItem]:
        validated: List[RecommendationItem] = []
        seen_series: Set[str] = set()
        for item in ranked_items:
            if constraints.strict_types and item.type not in constraints.strict_types:
                continue
            identity = build_series_identity(item.title, item.type)
            series_key = item.series_key or identity.series_key
            if series_key in seen_series:
                continue
            seen_series.add(series_key)

            item.series_key = series_key
            item.series_title_zh = item.series_title_zh or identity.series_display_title_zh
            item.is_series_representative = True
            if constraints.language_preference == "zh_preferred" and item.series_title_zh:
                item.title = item.series_title_zh
            validated.append(item)
        return validated

    def _candidate_to_response(self, candidate: CandidateItem, score: float, reason: str) -> RecommendationItem:
        series_key = self._candidate_series_key(candidate)
        series_title_zh = self._candidate_series_title(candidate)
        return RecommendationItem(
            subject_id=candidate.subject_id,
            title=candidate.title,
            type=candidate.type,
            year=candidate.year,
            douban_url=candidate.douban_url,
            score=score,
            reason=reason,
            series_key=series_key,
            series_title_zh=series_title_zh,
            is_series_representative=True,
        )

    def _candidate_series_key(self, candidate: CandidateItem) -> str:
        value = (candidate.metadata or {}).get("series_key")
        if value:
            return value
        return build_series_identity(candidate.title, candidate.type).series_key

    def _candidate_series_title(self, candidate: CandidateItem) -> str:
        value = (candidate.metadata or {}).get("series_title_zh")
        if value:
            return value
        return build_series_identity(candidate.title, candidate.type).series_display_title_zh

    def _friend_reason(self, candidate: CandidateItem) -> Optional[str]:
        metadata = candidate.metadata or {}
        try:
            friend_count = int(str(metadata.get("friend_count", "0")) or "0")
        except ValueError:
            friend_count = 0
        if friend_count <= 0:
            return None

        try:
            avg_rating = float(str(metadata.get("friend_avg_rating", "0")) or "0")
        except ValueError:
            avg_rating = 0.0
        try:
            weight_sum = float(str(metadata.get("friend_weight_sum", "0")) or "0")
        except ValueError:
            weight_sum = 0.0
        try:
            weight_avg = float(str(metadata.get("friend_weight_avg", "1")) or "1")
        except ValueError:
            weight_avg = 1.0
        friend_names = str(metadata.get("friend_users", "")).strip()
        latest_date = str(metadata.get("friend_latest_date", "")).strip()
        date_hint = latest_date[:10] if len(latest_date) >= 10 else ""
        weighted_hint = abs(weight_avg - 1.0) > 1e-6
        if friend_count == 1 and friend_names:
            parts = [f"{friend_names}高分读过", f"评分{avg_rating:.1f}"]
            if weighted_hint:
                parts.append(f"权重{weight_sum:.2f}")
            if date_hint:
                parts.append(f"最近于{date_hint}")
            return f"{parts[0]}（{'，'.join(parts[1:])}）"

        parts = [f"{friend_count}位好友高分读过", f"均分{avg_rating:.1f}"]
        if weighted_hint:
            parts.append(f"权重和{weight_sum:.2f}")
        if date_hint:
            parts.append(f"最近于{date_hint}")
        return f"{parts[0]}（{'，'.join(parts[1:])}）"

    def _candidate_friend_latest_ts(self, candidate: CandidateItem) -> float:
        metadata = candidate.metadata or {}
        value = metadata.get("friend_latest_ts")
        if value is None:
            return 0.0
        try:
            return float(str(value))
        except ValueError:
            return 0.0

    def _to_response_items(self, ranked: Sequence[RecommendationItem], top_k: int) -> List[RecommendationItem]:
        return list(ranked[:top_k])

    def _fallback_candidates(
        self,
        query: str,
        history: Sequence[Tuple[Interaction, Item]],
        seen_subject_ids: Set[str],
        constraints: QueryConstraints,
    ) -> List[CandidateItem]:
        seen_titles = {item.title.strip().lower() for _, item in history if item.title}
        now_year = datetime.utcnow().year
        movie_hint = "电影" in query
        tv_hint = "剧" in query or "电视剧" in query
        book_hint = "书" in query or "阅读" in query
        recent_hint = "近" in query or "最近" in query

        rows = []
        require_topic_match = bool(constraints.topic_tags)
        for entry in FALLBACK_CANDIDATE_CATALOG:
            subject_id = entry["subject_id"]
            title = entry["title"]
            item_type = entry["type"]
            year = entry.get("year")
            tags = set(entry.get("tags", []))

            if constraints.strict_types and item_type not in constraints.strict_types:
                continue
            if require_topic_match and not (constraints.topic_tags & tags):
                continue
            if subject_id in seen_subject_ids:
                continue
            if title.strip().lower() in seen_titles:
                continue

            score = float(entry["score"])
            if recent_hint and year and year >= now_year - 5:
                score += 0.2
            if movie_hint and item_type == "movie":
                score += 0.15
            if tv_hint and item_type == "tv":
                score += 0.15
            if book_hint and item_type == "book":
                score += 0.15

            rows.append((score, entry))

        rows.sort(key=lambda row: (row[0], row[1].get("year") or 0), reverse=True)
        return [
            CandidateItem(
                subject_id=entry["subject_id"],
                title=entry["title"],
                type=entry["type"],
                year=entry.get("year"),
                douban_url=entry["douban_url"],
                score=round(float(score), 4),
                metadata={
                    "display_title_zh": entry.get("display_title_zh", ""),
                    "tags": ",".join(entry.get("tags", [])),
                },
            )
            for score, entry in rows
        ]

    def _build_applied_constraints(
        self,
        constraints: QueryConstraints,
        deduped_series_count: int,
    ) -> AppliedConstraints:
        return AppliedConstraints(
            strict_types=sorted(constraints.strict_types),
            series_grouping=True,
            title_language=constraints.language_preference,
            deduped_series_count=deduped_series_count,
        )
