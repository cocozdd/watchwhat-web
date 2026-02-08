from app.schemas import RecommendResponse
from app.services.douban_username import infer_sync_media_types, normalize_douban_username


def test_normalize_douban_username_plain_value():
    assert normalize_douban_username("demo_user") == "demo_user"


def test_normalize_douban_username_from_profile_url():
    assert normalize_douban_username("https://www.douban.com/people/demo_user/") == "demo_user"


def test_normalize_douban_username_from_collect_url():
    assert (
        normalize_douban_username("https://movie.douban.com/people/demo_user/collect?start=15")
        == "demo_user"
    )


def test_infer_sync_media_types_for_book_mine_url():
    media_types = infer_sync_media_types("https://book.douban.com/mine?status=collect", "__mine__")
    assert media_types == ["book"]


def test_infer_sync_media_types_for_movie_mine_url():
    media_types = infer_sync_media_types("https://movie.douban.com/mine?status=collect", "__mine__")
    assert media_types == ["movie_tv"]


def test_sync_endpoint_accepts_douban_url(client, monkeypatch):
    captured = {}

    def fake_start_sync(*, source, username, cookie, force_full, media_types):
        captured["source"] = source
        captured["username"] = username
        captured["cookie"] = cookie
        captured["force_full"] = force_full
        captured["media_types"] = media_types
        return "job-url-1"

    monkeypatch.setattr("app.routers.sync.sync_job_runner.start_sync", fake_start_sync)

    response = client.post(
        "/api/sync",
        json={
            "source": "douban",
            "username": "https://www.douban.com/people/demo_user/",
            "cookie": None,
            "force_full": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["job_id"] == "job-url-1"
    assert captured["username"] == "demo_user"
    assert captured["media_types"] == ["movie_tv", "book"]


def test_recommend_endpoint_accepts_douban_url(client, monkeypatch):
    captured = {}

    def fake_recommend(*, source, username, query, top_k, allow_followup, friend_usernames, friend_weights):
        captured["source"] = source
        captured["username"] = username
        captured["query"] = query
        captured["top_k"] = top_k
        captured["allow_followup"] = allow_followup
        captured["friend_usernames"] = friend_usernames
        captured["friend_weights"] = friend_weights
        return RecommendResponse(status="ok", items=[], profile_summary="")

    monkeypatch.setattr("app.routers.recommend.engine.recommend", fake_recommend)

    response = client.post(
        "/api/recommend",
        json={
            "source": "douban",
            "username": "https://movie.douban.com/people/demo_user/collect?start=0",
            "query": "想看高分",
            "top_k": 20,
            "allow_followup": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert captured["username"] == "demo_user"
    assert captured["friend_usernames"] == []
    assert captured["friend_weights"] == {}


def test_sync_endpoint_preserves_user_input_username_with_cookie(client, monkeypatch):
    captured = {}

    def fake_start_sync(*, source, username, cookie, force_full, media_types):
        captured["source"] = source
        captured["username"] = username
        captured["cookie"] = cookie
        captured["force_full"] = force_full
        captured["media_types"] = media_types
        return "job-cookie-1"

    monkeypatch.setattr("app.routers.sync.sync_job_runner.start_sync", fake_start_sync)

    response = client.post(
        "/api/sync",
        json={
            "source": "douban",
            "username": "my_input_user",
            "cookie": "dbcl2=abc123; ck=xyz",
            "force_full": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["job_id"] == "job-cookie-1"
    assert captured["username"] == "my_input_user"


def test_sync_endpoint_respects_book_only_scope(client, monkeypatch):
    captured = {}

    def fake_start_sync(*, source, username, cookie, force_full, media_types):
        captured["source"] = source
        captured["username"] = username
        captured["cookie"] = cookie
        captured["force_full"] = force_full
        captured["media_types"] = media_types
        return "job-book-only-1"

    monkeypatch.setattr("app.routers.sync.sync_job_runner.start_sync", fake_start_sync)

    response = client.post(
        "/api/sync",
        json={
            "source": "douban",
            "username": "demo_user",
            "cookie": None,
            "force_full": False,
            "sync_scope": "book",
        },
    )
    assert response.status_code == 200
    assert response.json()["job_id"] == "job-book-only-1"
    assert captured["media_types"] == ["book"]
