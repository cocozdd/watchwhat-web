from pathlib import Path

from app.services.douban_parser import parse_history_page
from app.services.douban_username import normalize_douban_username


def test_normalize_douban_mine_url():
    assert normalize_douban_username("https://book.douban.com/mine?status=collect") == "__mine__"


def test_sync_endpoint_accepts_mine_url_when_cookie_exists(client, monkeypatch):
    from app.services.cookie_capture import cookie_capture_manager

    cookie_capture_manager.set_cookie("douban", "dbcl2=12345678:xyz; ck=abc")

    captured = {}

    def fake_start_sync(*, source, username, cookie, force_full, media_types):
        captured["source"] = source
        captured["username"] = username
        captured["cookie"] = cookie
        captured["force_full"] = force_full
        captured["media_types"] = media_types
        return "job-mine-1"

    monkeypatch.setattr("app.routers.sync.sync_job_runner.start_sync", fake_start_sync)

    response = client.post(
        "/api/sync",
        json={
            "source": "douban",
            "username": "https://book.douban.com/mine?status=collect",
            "cookie": None,
            "force_full": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "job-mine-1"
    assert captured["username"] == "__mine__"
    assert captured["cookie"] is not None
    assert captured["media_types"] == ["book"]


def test_sync_endpoint_rejects_mine_url_without_cookie(client):
    from app.services.cookie_capture import cookie_capture_manager

    cookie_capture_manager.clear_cookie("douban")
    response = client.post(
        "/api/sync",
        json={
            "source": "douban",
            "username": "https://book.douban.com/mine?status=collect",
            "cookie": None,
            "force_full": False,
        },
    )

    assert response.status_code == 400
    assert "requires login cookie" in response.json()["detail"]


def test_parse_mine_book_page_generic():
    html = Path("tests/fixtures/douban_book_mine_page.html").read_text(encoding="utf-8")
    page = parse_history_page(html, media_type="book", current_cursor=0)

    assert len(page.records) == 2
    assert page.records[0].subject_id == "37415823"
    assert page.records[0].type == "book"
    assert page.records[0].rating == 8.0
    assert page.records[1].subject_id == "27590675"
    assert page.next_cursor == 15
