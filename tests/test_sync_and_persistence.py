from datetime import datetime

from sqlmodel import select

from app.models import Interaction, Item, User
from app.services.adapters.base import CandidateItem, HistoryPage, HistoryRecord, SourceAdapter


class FakeDoubanAdapter(SourceAdapter):
    def fetch_history(self, username, cookie, page_cursor, media_type):
        if media_type == "movie_tv" and page_cursor == 0:
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="m_seen_1",
                        title="Seen Movie",
                        type="movie",
                        year=2022,
                        douban_url="https://movie.douban.com/subject/m_seen_1/",
                        rating=10.0,
                        interacted_at=datetime(2025, 1, 1),
                    )
                ],
                next_cursor=None,
            )
        if media_type == "book" and page_cursor == 0:
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="b_seen_1",
                        title="Seen Book",
                        type="book",
                        year=2021,
                        douban_url="https://book.douban.com/subject/b_seen_1/",
                        rating=8.0,
                        interacted_at=datetime(2025, 1, 2),
                    )
                ],
                next_cursor=None,
            )
        return HistoryPage(records=[], next_cursor=None)

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return [
            CandidateItem(
                subject_id="m_new_1",
                title="New Movie",
                type="movie",
                year=2024,
                douban_url="https://movie.douban.com/subject/m_new_1/",
                score=0.9,
            )
        ]


def test_sync_and_data_persistence(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FakeDoubanAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FakeDoubanAdapter())

    res = client.post(
        "/api/sync",
        json={"source": "douban", "username": "demo_user", "cookie": None, "force_full": False},
    )
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    status = client.get(f"/api/sync/{job_id}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "done"
    assert payload["effective_username"] == "demo_user"
    assert payload["counts"]["start"] == {"movie_tv": 0, "book": 0, "total": 0}
    assert payload["counts"]["end"] == {"movie_tv": 1, "book": 1, "total": 2}
    assert payload["counts"]["added"] == {"movie_tv": 1, "book": 1, "total": 2}
    assert len(payload["added_preview"]) == 2
    assert payload["added_preview"][0]["title"] == "Seen Movie"
    assert payload["added_preview"][1]["title"] == "Seen Book"

    user = db_session.exec(select(User).where(User.username == "demo_user")).first()
    assert user is not None

    items = db_session.exec(select(Item)).all()
    assert len(items) == 2

    interactions = db_session.exec(select(Interaction)).all()
    assert len(interactions) == 2

    # Simulate app restart by creating a new client and re-reading persistent DB.
    with client:
        pass

    from app.db import get_engine
    from sqlmodel import Session

    with Session(get_engine()) as new_session:
        persisted = new_session.exec(select(User).where(User.username == "demo_user")).first()
        assert persisted is not None


def test_library_endpoint_returns_synced_items(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FakeDoubanAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FakeDoubanAdapter())

    res = client.post(
        "/api/sync",
        json={"source": "douban", "username": "demo_user", "cookie": None, "force_full": False},
    )
    assert res.status_code == 200

    library = client.get(
        "/api/library",
        params={"source": "douban", "username": "demo_user", "limit": 10, "offset": 0},
    )
    assert library.status_code == 200
    payload = library.json()
    assert payload["total"] == 2
    assert payload["movie_tv_count"] == 1
    assert payload["book_count"] == 1
    assert len(payload["items"]) == 2
