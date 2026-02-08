from app.services.adapters.base import HistoryPage, SourceAdapter


class RecordingAdapter(SourceAdapter):
    seen_cookies = []

    def fetch_history(self, username, cookie, page_cursor, media_type):
        RecordingAdapter.seen_cookies.append(cookie)
        return HistoryPage(records=[], next_cursor=None)

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return []


def test_sync_uses_auto_captured_cookie_when_cookie_missing(client, monkeypatch):
    from app.services.cookie_capture import cookie_capture_manager

    RecordingAdapter.seen_cookies = []
    cookie_capture_manager.set_cookie("douban", "dbcl2=abc; ck=xyz")

    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: RecordingAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: RecordingAdapter())

    res = client.post(
        "/api/sync",
        json={"source": "douban", "username": "demo_user", "cookie": None, "force_full": False},
    )
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    status = client.get(f"/api/sync/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "done"

    assert "dbcl2=abc; ck=xyz" in RecordingAdapter.seen_cookies


def test_cookie_auto_capture_api(client, monkeypatch):
    from app.services.cookie_capture import CookieCaptureStatus

    monkeypatch.setattr(
        "app.routers.sync.cookie_capture_manager.start_auto_capture",
        lambda source: CookieCaptureStatus(
            job_id="job-1",
            status="running",
            message="capture started",
            has_cookie=False,
        ),
    )
    monkeypatch.setattr(
        "app.routers.sync.cookie_capture_manager.get_capture_status",
        lambda job_id: CookieCaptureStatus(
            job_id=job_id,
            status="done",
            message="cookie captured",
            has_cookie=True,
        ),
    )

    start = client.post("/api/cookie/auto/start", json={"source": "douban"})
    assert start.status_code == 200
    assert start.json()["job_id"] == "job-1"
    assert start.json()["status"] == "running"

    status = client.get("/api/cookie/auto/job-1")
    assert status.status_code == 200
    payload = status.json()
    assert payload["job_id"] == "job-1"
    assert payload["status"] == "done"
    assert payload["has_cookie"] is True


def test_manual_cookie_is_persisted_for_followup_sync(client, monkeypatch):
    from app.services.cookie_capture import cookie_capture_manager

    RecordingAdapter.seen_cookies = []
    cookie_capture_manager.clear_cookie("douban")

    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: RecordingAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: RecordingAdapter())

    first = client.post(
        "/api/sync",
        json={
            "source": "douban",
            "username": "demo_user",
            "cookie": "dbcl2=manual_cookie; ck=manual_ck",
            "force_full": False,
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/sync",
        json={"source": "douban", "username": "demo_user", "cookie": None, "force_full": False},
    )
    assert second.status_code == 200

    assert "dbcl2=manual_cookie; ck=manual_ck" in RecordingAdapter.seen_cookies
