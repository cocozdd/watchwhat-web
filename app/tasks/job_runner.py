from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional

from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine
from app.models import Interaction, Item, SyncJob, User
from app.services.adapters import get_source_adapter
from app.services.adapters.base import HistoryRecord


class SyncJobRunner:
    def __init__(self):
        self.settings = get_settings()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._job_counts: Dict[str, dict] = {}
        self._job_counts_lock = Lock()

    def start_sync(
        self,
        source: str,
        username: str,
        cookie: Optional[str],
        force_full: bool,
        media_types: Optional[List[str]] = None,
    ) -> str:
        selected_media = media_types or ["movie_tv", "book"]
        with Session(get_engine()) as session:
            user = self._get_or_create_user(session, source=source, username=username)
            job = SyncJob(user_id=user.id, source=source, status="queued", done=0, total=0, message="queued")
            session.add(job)
            session.commit()
            session.refresh(job)

        if self.settings.sync_inline:
            self._run_sync(job.id, source, username, cookie, force_full, selected_media)
        else:
            self.executor.submit(self._run_sync, job.id, source, username, cookie, force_full, selected_media)

        return job.id

    def _run_sync(
        self,
        job_id: str,
        source: str,
        username: str,
        cookie: Optional[str],
        force_full: bool,
        media_types: List[str],
    ) -> None:
        del force_full  # Reserved for future incremental/full strategy.
        start_counts = self._empty_count_snapshot()
        self._set_job_counts(job_id, start=start_counts, end=start_counts)

        try:
            adapter = get_source_adapter(source)
            with Session(get_engine()) as session:
                job = session.get(SyncJob, job_id)
                if job is None:
                    return
                start_counts = self._compute_user_counts(session, job.user_id)
                self._set_job_counts(job_id, start=start_counts, end=start_counts)
                job.status = "running"
                job.message = "sync started"
                session.add(job)
                session.commit()

            done_pages = 0
            total_pages = 0
            media_failures: List[str] = []

            for media_type in media_types:
                cursor = 0
                pages_for_type = 0
                while True:
                    pages_for_type += 1
                    if pages_for_type > self.settings.max_history_pages:
                        break

                    total_pages += 1
                    self._update_job(job_id, total=total_pages, message=f"syncing {media_type} page {pages_for_type}")
                    try:
                        page = adapter.fetch_history(
                            username=username,
                            cookie=cookie,
                            page_cursor=cursor,
                            media_type=media_type,
                        )
                    except Exception as media_exc:
                        media_failures.append(f"{media_type}: {media_exc}")
                        self._update_job(job_id, message=f"skip {media_type}: {media_exc}")
                        break

                    with Session(get_engine()) as session:
                        job = session.get(SyncJob, job_id)
                        if job is None:
                            return

                        for record in page.records:
                            item = self._upsert_item(session, source=source, record=record)
                            created = self._upsert_interaction(
                                session,
                                user_id=job.user_id,
                                item_id=item.id,
                                record=record,
                            )
                            if created:
                                self._append_added_preview(job_id, record)

                        session.commit()

                    done_pages += 1
                    self._update_job(job_id, done=done_pages)

                    if page.next_cursor is None:
                        break
                    cursor = page.next_cursor

            if done_pages == 0 and media_failures:
                raise RuntimeError(f"all media sync failed: {'; '.join(media_failures)}")

            with Session(get_engine()) as session:
                job = session.get(SyncJob, job_id)
                if job is None:
                    return
                user = session.get(User, job.user_id)
                end_counts = self._compute_user_counts(session, job.user_id)
                self._set_job_counts(job_id, end=end_counts)
                if user is not None:
                    user.last_synced_at = datetime.utcnow()
                    user.updated_at = datetime.utcnow()
                    session.add(user)
                job.status = "done"
                count_suffix = self._format_counts_suffix(self.get_job_counts(job_id))
                if media_failures:
                    job.message = (
                        f"sync completed with partial failures: {'; '.join(media_failures)}"
                        f"{count_suffix}"
                    )
                else:
                    job.message = f"sync completed{count_suffix}"
                job.finished_at = datetime.utcnow()
                session.add(job)
                session.commit()
        except Exception as exc:
            with Session(get_engine()) as session:
                job = session.get(SyncJob, job_id)
                if job is None:
                    return
                end_counts = self._compute_user_counts(session, job.user_id)
                self._set_job_counts(job_id, end=end_counts)
                count_suffix = self._format_counts_suffix(self.get_job_counts(job_id))
                job.status = "failed"
                job.error_message = str(exc)
                job.message = f"sync failed: {exc}{count_suffix}"
                job.finished_at = datetime.utcnow()
                session.add(job)
                session.commit()

    def _update_job(
        self,
        job_id: str,
        done: Optional[int] = None,
        total: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        with Session(get_engine()) as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return
            if done is not None:
                job.done = done
            if total is not None:
                job.total = total
            if message is not None:
                job.message = message
            session.add(job)
            session.commit()

    def _get_or_create_user(self, session: Session, source: str, username: str) -> User:
        stmt = select(User).where(User.source == source, User.username == username)
        user = session.exec(stmt).first()
        if user is not None:
            user.updated_at = datetime.utcnow()
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

        user = User(source=source, username=username)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    def _upsert_item(self, session: Session, source: str, record: HistoryRecord) -> Item:
        stmt = select(Item).where(Item.source == source, Item.subject_id == record.subject_id)
        item = session.exec(stmt).first()
        if item is None:
            item = Item(
                source=source,
                subject_id=record.subject_id,
                type=record.type,
                title=record.title,
                year=record.year,
                douban_url=record.douban_url,
                meta_json="{}",
                updated_at=datetime.utcnow(),
            )
            session.add(item)
            session.flush()
            return item

        item.type = record.type
        item.title = record.title
        item.year = record.year
        item.douban_url = record.douban_url
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.flush()
        return item

    def _upsert_interaction(self, session: Session, user_id: int, item_id: int, record: HistoryRecord) -> bool:
        stmt = select(Interaction).where(Interaction.user_id == user_id, Interaction.item_id == item_id)
        interaction = session.exec(stmt).first()
        created = interaction is None
        if interaction is None:
            interaction = Interaction(
                user_id=user_id,
                item_id=item_id,
                rating=record.rating,
                interacted_at=record.interacted_at,
                comment=record.comment,
            )
        else:
            interaction.rating = record.rating
            interaction.interacted_at = record.interacted_at
            interaction.comment = record.comment
        session.add(interaction)
        return created

    def get_job_counts(self, job_id: str) -> Optional[dict]:
        with self._job_counts_lock:
            summary = self._job_counts.get(job_id)
            if summary is None:
                return None
            return {
                "start": dict(summary["start"]),
                "end": dict(summary["end"]),
                "added": dict(summary["added"]),
            }

    def get_job_added_preview(self, job_id: str) -> List[dict]:
        with self._job_counts_lock:
            summary = self._job_counts.get(job_id)
            if summary is None:
                return []
            return list(summary.get("added_preview", []))

    def _set_job_counts(
        self,
        job_id: str,
        start: Optional[dict] = None,
        end: Optional[dict] = None,
    ) -> None:
        with self._job_counts_lock:
            summary = self._job_counts.setdefault(
                job_id,
                {
                    "start": self._empty_count_snapshot(),
                    "end": self._empty_count_snapshot(),
                    "added": self._empty_count_snapshot(),
                    "added_preview": [],
                },
            )
            if start is not None:
                summary["start"] = dict(start)
            if end is not None:
                summary["end"] = dict(end)

            summary["added"] = {
                "movie_tv": max(0, summary["end"]["movie_tv"] - summary["start"]["movie_tv"]),
                "book": max(0, summary["end"]["book"] - summary["start"]["book"]),
                "total": max(0, summary["end"]["total"] - summary["start"]["total"]),
            }

    def _append_added_preview(self, job_id: str, record: HistoryRecord) -> None:
        with self._job_counts_lock:
            summary = self._job_counts.setdefault(
                job_id,
                {
                    "start": self._empty_count_snapshot(),
                    "end": self._empty_count_snapshot(),
                    "added": self._empty_count_snapshot(),
                    "added_preview": [],
                },
            )
            preview = summary.setdefault("added_preview", [])
            if len(preview) >= 20:
                return
            preview.append(
                {
                    "subject_id": record.subject_id,
                    "title": record.title,
                    "type": record.type,
                    "year": record.year,
                    "douban_url": record.douban_url,
                }
            )

    @staticmethod
    def _empty_count_snapshot() -> dict:
        return {"movie_tv": 0, "book": 0, "total": 0}

    def _compute_user_counts(self, session: Session, user_id: int) -> dict:
        statement = select(Item.type).join(Interaction, Interaction.item_id == Item.id).where(Interaction.user_id == user_id)
        item_types = session.exec(statement).all()
        movie_tv = 0
        book = 0
        for item_type in item_types:
            if item_type in {"movie", "tv"}:
                movie_tv += 1
            elif item_type == "book":
                book += 1
        return {"movie_tv": movie_tv, "book": book, "total": movie_tv + book}

    def _format_counts_suffix(self, summary: Optional[dict]) -> str:
        if not summary:
            return ""
        start = summary["start"]
        end = summary["end"]
        added = summary["added"]
        return (
            " | counts: "
            f"start(movie_tv={start['movie_tv']},book={start['book']},total={start['total']}) "
            f"end(movie_tv={end['movie_tv']},book={end['book']},total={end['total']}) "
            f"added(movie_tv={added['movie_tv']},book={added['book']},total={added['total']})"
        )


sync_job_runner = SyncJobRunner()
