from datetime import datetime

from app.services.adapters.base import CandidateItem, HistoryPage, HistoryRecord, SourceAdapter


class FakeDoubanAdapter(SourceAdapter):
    def fetch_history(self, username, cookie, page_cursor, media_type):
        if page_cursor > 0:
            return HistoryPage(records=[], next_cursor=None)
        records = [
            HistoryRecord(
                subject_id="seen_movie_1",
                title="Seen Movie 1",
                type="movie",
                year=2020,
                douban_url="https://movie.douban.com/subject/seen_movie_1/",
                rating=10.0,
                interacted_at=datetime(2025, 1, 1),
            )
        ]
        if media_type == "book":
            records = [
                HistoryRecord(
                    subject_id="seen_book_1",
                    title="Seen Book 1",
                    type="book",
                    year=2018,
                    douban_url="https://book.douban.com/subject/seen_book_1/",
                    rating=8.0,
                    interacted_at=datetime(2025, 1, 2),
                )
            ]
        return HistoryPage(records=records, next_cursor=None)

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return [
            CandidateItem(
                subject_id="seen_movie_1",
                title="Already Seen",
                type="movie",
                year=2020,
                douban_url="https://movie.douban.com/subject/seen_movie_1/",
                score=0.5,
            ),
            CandidateItem(
                subject_id="new_movie_1",
                title="Brand New Movie",
                type="movie",
                year=2024,
                douban_url="https://movie.douban.com/subject/new_movie_1/",
                score=0.95,
            ),
            CandidateItem(
                subject_id="new_book_1",
                title="Brand New Book",
                type="book",
                year=2023,
                douban_url="https://book.douban.com/subject/new_book_1/",
                score=0.92,
            ),
        ]


class EmptyCandidateAdapter(FakeDoubanAdapter):
    def fetch_candidate_pool(self, seed_items, cookie=None):
        return []


class SeriesNoiseAdapter(FakeDoubanAdapter):
    def fetch_candidate_pool(self, seed_items, cookie=None):
        return [
            CandidateItem(
                subject_id="op_eng_v1",
                title="One Piece Vol.1",
                type="book",
                year=2005,
                douban_url="https://book.douban.com/subject/op_eng_v1/",
                score=0.96,
            ),
            CandidateItem(
                subject_id="op_zh_v2",
                title="海贼王 第2卷",
                type="book",
                year=2006,
                douban_url="https://book.douban.com/subject/op_zh_v2/",
                score=0.95,
            ),
            CandidateItem(
                subject_id="op_jp_v3",
                title="ワンピース 3",
                type="book",
                year=2007,
                douban_url="https://book.douban.com/subject/op_jp_v3/",
                score=0.94,
            ),
            CandidateItem(
                subject_id="new_book_2",
                title="三体",
                type="book",
                year=2008,
                douban_url="https://book.douban.com/subject/new_book_2/",
                score=0.91,
            ),
        ]


class MysterySeenAdapter(FakeDoubanAdapter):
    def fetch_history(self, username, cookie, page_cursor, media_type):
        if page_cursor > 0:
            return HistoryPage(records=[], next_cursor=None)
        if media_type == "book":
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="seen_mystery_1",
                        title="嫌疑人X的献身",
                        type="book",
                        year=2005,
                        douban_url="https://book.douban.com/subject/2307791/",
                        rating=9.0,
                        interacted_at=datetime(2025, 1, 2),
                    )
                ],
                next_cursor=None,
            )
        return HistoryPage(records=[], next_cursor=None)

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return []


class CrossLanguageDuplicateAdapter(FakeDoubanAdapter):
    def fetch_history(self, username, cookie, page_cursor, media_type):
        if page_cursor > 0:
            return HistoryPage(records=[], next_cursor=None)
        if media_type != "book":
            return HistoryPage(records=[], next_cursor=None)
        return HistoryPage(
            records=[
                HistoryRecord(
                    subject_id="jp_seen_34717263",
                    title="そして誰も死ななかった",
                    type="book",
                    year=2019,
                    douban_url="https://book.douban.com/subject/34717263/",
                    rating=10.0,
                    interacted_at=datetime(2025, 1, 2),
                )
            ],
            next_cursor=None,
        )

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return [
            CandidateItem(
                subject_id="zh_alias_36435335",
                title="无人逝去",
                type="book",
                year=2023,
                douban_url="https://book.douban.com/subject/36435335/",
                score=0.99,
            ),
            CandidateItem(
                subject_id="book_new_unique_1",
                title="钟表馆事件",
                type="book",
                year=1989,
                douban_url="https://book.douban.com/subject/book_new_unique_1/",
                score=0.85,
            ),
        ]


class FriendCollaborativeAdapter(FakeDoubanAdapter):
    def fetch_history(self, username, cookie, page_cursor, media_type):
        if page_cursor > 0:
            return HistoryPage(records=[], next_cursor=None)
        if media_type != "book":
            return HistoryPage(records=[], next_cursor=None)
        if username == "demo_user":
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="seen_book_1",
                        title="Seen Book 1",
                        type="book",
                        year=2018,
                        douban_url="https://book.douban.com/subject/seen_book_1/",
                        rating=8.0,
                        interacted_at=datetime(2025, 1, 2),
                    )
                ],
                next_cursor=None,
            )
        if username == "friend_a":
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="friend_shared_book",
                        title="解忧杂货店",
                        type="book",
                        year=2012,
                        douban_url="https://book.douban.com/subject/friend_shared_book/",
                        rating=9.0,
                        interacted_at=datetime(2025, 1, 3),
                    ),
                    HistoryRecord(
                        subject_id="friend_only_a_book",
                        title="白夜行",
                        type="book",
                        year=1999,
                        douban_url="https://book.douban.com/subject/friend_only_a_book/",
                        rating=8.0,
                        interacted_at=datetime(2025, 1, 4),
                    ),
                ],
                next_cursor=None,
            )
        if username == "friend_b":
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="friend_shared_book",
                        title="解忧杂货店",
                        type="book",
                        year=2012,
                        douban_url="https://book.douban.com/subject/friend_shared_book/",
                        rating=8.5,
                        interacted_at=datetime(2025, 1, 5),
                    )
                ],
                next_cursor=None,
            )
        return HistoryPage(records=[], next_cursor=None)

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return []


class WeightedFriendSignalAdapter(FakeDoubanAdapter):
    def fetch_history(self, username, cookie, page_cursor, media_type):
        if page_cursor > 0:
            return HistoryPage(records=[], next_cursor=None)
        if media_type != "book":
            return HistoryPage(records=[], next_cursor=None)
        if username == "demo_user":
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="seen_book_1",
                        title="Seen Book 1",
                        type="book",
                        year=2018,
                        douban_url="https://book.douban.com/subject/seen_book_1/",
                        rating=8.0,
                        interacted_at=datetime(2025, 1, 2),
                    )
                ],
                next_cursor=None,
            )
        if username == "friend_a":
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="weighted_book_a",
                        title="A Book",
                        type="book",
                        year=2020,
                        douban_url="https://book.douban.com/subject/weighted_book_a/",
                        rating=8.0,
                        interacted_at=datetime(2025, 1, 1),
                    )
                ],
                next_cursor=None,
            )
        if username == "friend_b":
            return HistoryPage(
                records=[
                    HistoryRecord(
                        subject_id="weighted_book_b",
                        title="B Book",
                        type="book",
                        year=2020,
                        douban_url="https://book.douban.com/subject/weighted_book_b/",
                        rating=10.0,
                        interacted_at=datetime(2025, 1, 1),
                    )
                ],
                next_cursor=None,
            )
        return HistoryPage(records=[], next_cursor=None)

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return []


def _sync_seed_data(client):
    res = client.post(
        "/api/sync",
        json={"source": "douban", "username": "demo_user", "cookie": None, "force_full": False},
    )
    assert res.status_code == 200


def test_recommend_excludes_seen_items(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FakeDoubanAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FakeDoubanAdapter())

    _sync_seed_data(client)

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "想看轻松高分",
            "top_k": 5,
            "allow_followup": True,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    subject_ids = [x["subject_id"] for x in payload["items"]]
    assert "seen_movie_1" not in subject_ids
    assert "new_movie_1" in subject_ids


def test_followup_flow(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FakeDoubanAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FakeDoubanAdapter())

    _sync_seed_data(client)

    first = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "随便",
            "top_k": 5,
            "allow_followup": True,
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["status"] == "need_followup"
    assert first_payload["session_id"]

    followup = client.post(
        "/api/recommend/followup",
        json={"session_id": first_payload["session_id"], "answer": "优先近五年"},
    )
    assert followup.status_code == 200
    follow_payload = followup.json()
    assert follow_payload["status"] == "ok"
    assert len(follow_payload["items"]) >= 1


def test_recommend_falls_back_when_external_candidates_empty(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: EmptyCandidateAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: EmptyCandidateAdapter())

    _sync_seed_data(client)

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "想看近五年电影",
            "top_k": 5,
            "allow_followup": False,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    assert "候选来源: 本地回退库" in payload["profile_summary"]


def test_recommend_strict_book_query_filters_non_book_items(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FakeDoubanAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FakeDoubanAdapter())

    _sync_seed_data(client)

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "推荐一些高分小说",
            "top_k": 10,
            "allow_followup": False,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    assert all(item["type"] == "book" for item in payload["items"])
    assert payload["applied_constraints"]["strict_types"] == ["book"]
    assert payload["applied_constraints"]["series_grouping"] is True
    assert payload["applied_constraints"]["title_language"] == "zh_preferred"


def test_recommend_dedupes_series_and_prefers_chinese_series_title(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: SeriesNoiseAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: SeriesNoiseAdapter())

    _sync_seed_data(client)

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "推荐书籍，偏热血冒险",
            "top_k": 10,
            "allow_followup": False,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]

    series_keys = [item.get("series_key") for item in payload["items"] if item.get("series_key")]
    assert len(series_keys) == len(set(series_keys))

    grouped = [item for item in payload["items"] if item.get("series_title_zh") == "海贼王"]
    assert len(grouped) <= 1
    if grouped:
        assert grouped[0]["title"] == "海贼王"
        assert grouped[0]["is_series_representative"] is True
    assert payload["applied_constraints"]["deduped_series_count"] >= 1


def test_recommend_filters_cross_language_same_work_if_already_seen(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: CrossLanguageDuplicateAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: CrossLanguageDuplicateAdapter())

    _sync_seed_data(client)

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "推荐推理小说",
            "top_k": 10,
            "allow_followup": False,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    subject_ids = [item["subject_id"] for item in payload["items"]]
    assert "zh_alias_36435335" not in subject_ids


def test_recommend_book_sparse_candidates_returns_followup_not_cross_type(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: EmptyCandidateAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: EmptyCandidateAdapter())
    monkeypatch.setattr(
        "app.services.recommendation_engine.FALLBACK_CANDIDATE_CATALOG",
        [
            {
                "subject_id": "fallback-movie-only",
                "title": "Only Movie",
                "type": "movie",
                "year": 2024,
                "douban_url": "https://movie.douban.com/subject/fallback-movie-only/",
                "score": 0.9,
            }
        ],
    )

    _sync_seed_data(client)

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "推荐小说",
            "top_k": 10,
            "allow_followup": True,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "need_followup"
    assert "书籍候选不足" in payload["followup_question"]


def test_recommend_mystery_query_filters_fallback_by_topic_and_prefers_chinese_title(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: EmptyCandidateAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: EmptyCandidateAdapter())
    monkeypatch.setattr(
        "app.services.recommendation_engine.FALLBACK_CANDIDATE_CATALOG",
        [
            {
                "subject_id": "fallback-mystery-1",
                "title": "The Devotion of Suspect X",
                "display_title_zh": "嫌疑人X的献身",
                "type": "book",
                "year": 2005,
                "douban_url": "https://book.douban.com/subject/2307791/",
                "score": 0.93,
                "tags": ["mystery"],
            },
            {
                "subject_id": "fallback-scifi-1",
                "title": "The Three-Body Problem",
                "display_title_zh": "三体",
                "type": "book",
                "year": 2008,
                "douban_url": "https://book.douban.com/subject/2567698/",
                "score": 0.91,
                "tags": ["sci-fi"],
            },
        ],
    )

    _sync_seed_data(client)

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "推荐一些推理小说",
            "top_k": 5,
            "allow_followup": False,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    titles = [item["title"] for item in payload["items"]]
    assert "嫌疑人X的献身" in titles
    assert "三体" not in titles


def test_followup_answer_relaxes_topic_filter_when_user_says_anything(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: EmptyCandidateAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: EmptyCandidateAdapter())
    monkeypatch.setattr(
        "app.services.recommendation_engine.FALLBACK_CANDIDATE_CATALOG",
        [
            {
                "subject_id": "fallback-scifi-1",
                "title": "The Three-Body Problem",
                "display_title_zh": "三体",
                "type": "book",
                "year": 2008,
                "douban_url": "https://book.douban.com/subject/2567698/",
                "score": 0.91,
                "tags": ["sci-fi"],
            }
        ],
    )

    _sync_seed_data(client)

    first = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "推荐一些推理小说",
            "top_k": 20,
            "allow_followup": True,
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["status"] == "need_followup"
    assert first_payload["session_id"]

    second = client.post(
        "/api/recommend/followup",
        json={"session_id": first_payload["session_id"], "answer": "都可"},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["status"] == "ok"
    assert second_payload["items"]
    assert second_payload["items"][0]["title"] == "三体"


def test_recommend_does_not_auto_relax_topic_when_user_requested_mystery(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: MysterySeenAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: MysterySeenAdapter())
    monkeypatch.setattr(
        "app.services.recommendation_engine.FALLBACK_CANDIDATE_CATALOG",
        [
            {
                "subject_id": "fallback-mystery-1",
                "title": "嫌疑人X的献身",
                "display_title_zh": "嫌疑人X的献身",
                "type": "book",
                "year": 2005,
                "douban_url": "https://book.douban.com/subject/2307791/",
                "score": 0.93,
                "tags": ["mystery"],
            },
            {
                "subject_id": "fallback-scifi-1",
                "title": "三体",
                "display_title_zh": "三体",
                "type": "book",
                "year": 2008,
                "douban_url": "https://book.douban.com/subject/2567698/",
                "score": 0.91,
                "tags": ["sci-fi"],
            },
        ],
    )

    _sync_seed_data(client)

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "推荐一些推理小说",
            "top_k": 20,
            "allow_followup": False,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"] == []
    assert "暂无未读候选" in payload["profile_summary"]


def test_recommend_uses_friend_high_rating_signal_when_friend_data_available(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FriendCollaborativeAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FriendCollaborativeAdapter())

    for username in ("demo_user", "friend_a", "friend_b"):
        res = client.post(
            "/api/sync",
            json={"source": "douban", "username": username, "cookie": None, "force_full": False},
        )
        assert res.status_code == 200

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "推荐一些书籍",
            "top_k": 10,
            "allow_followup": False,
            "friend_usernames": ["friend_a", "friend_b"],
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    assert payload["items"][0]["subject_id"] == "friend_shared_book"
    assert "2位好友高分读过" in payload["items"][0]["reason"]


def test_recommend_accepts_friend_profile_urls(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FriendCollaborativeAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FriendCollaborativeAdapter())

    for username in ("demo_user", "friend_a", "friend_b"):
        res = client.post(
            "/api/sync",
            json={"source": "douban", "username": username, "cookie": None, "force_full": False},
        )
        assert res.status_code == 200

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "好友推荐一些书",
            "top_k": 10,
            "allow_followup": False,
            "friend_usernames": [
                "https://www.douban.com/people/friend_a/",
                "https://book.douban.com/people/friend_b/collect?start=0",
            ],
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    assert payload["items"][0]["subject_id"] == "friend_shared_book"


def test_recommend_friend_usernames_case_insensitive(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FriendCollaborativeAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FriendCollaborativeAdapter())

    for username in ("demo_user", "friend_a", "friend_b"):
        res = client.post(
            "/api/sync",
            json={"source": "douban", "username": username, "cookie": None, "force_full": False},
        )
        assert res.status_code == 200

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "好友推荐一些书",
            "top_k": 10,
            "allow_followup": False,
            "friend_usernames": ["FRIEND_A", "Friend_B"],
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    assert payload["items"][0]["subject_id"] == "friend_shared_book"


def test_recommend_friend_weights_default_to_one(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: WeightedFriendSignalAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: WeightedFriendSignalAdapter())

    for username in ("demo_user", "friend_a", "friend_b"):
        res = client.post(
            "/api/sync",
            json={"source": "douban", "username": username, "cookie": None, "force_full": False},
        )
        assert res.status_code == 200

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "好友推荐一些书",
            "top_k": 10,
            "allow_followup": False,
            "friend_usernames": ["friend_a", "friend_b"],
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    # default weight=1 for both friends, so higher rating book should win.
    assert payload["items"][0]["subject_id"] == "weighted_book_b"


def test_recommend_friend_weights_can_override_priority(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: WeightedFriendSignalAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: WeightedFriendSignalAdapter())

    for username in ("demo_user", "friend_a", "friend_b"):
        res = client.post(
            "/api/sync",
            json={"source": "douban", "username": username, "cookie": None, "force_full": False},
        )
        assert res.status_code == 200

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "好友推荐一些书",
            "top_k": 10,
            "allow_followup": False,
            "friend_usernames": ["friend_a", "friend_b"],
            "friend_weights": {"friend_a": 3, "friend_b": 1},
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["items"]
    # boosted weight pushes friend_a's item above higher raw rating from friend_b.
    assert payload["items"][0]["subject_id"] == "weighted_book_a"
    assert "权重" in payload["items"][0]["reason"]


def test_recommend_profile_summary_reports_loaded_friend_coverage(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FriendCollaborativeAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FriendCollaborativeAdapter())

    for username in ("demo_user", "friend_a", "friend_b"):
        res = client.post(
            "/api/sync",
            json={"source": "douban", "username": username, "cookie": None, "force_full": False},
        )
        assert res.status_code == 200

    res = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "demo_user",
            "query": "好友推荐一些书",
            "top_k": 10,
            "allow_followup": False,
            "friend_usernames": ["friend_a", "friend_b", "friend_missing"],
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert "好友已加载 2/3 位" in payload["profile_summary"]
