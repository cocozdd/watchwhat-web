from datetime import datetime

from sqlmodel import select

from app.models import User
from app.services.adapters.base import CandidateItem, HistoryPage, HistoryRecord, SourceAdapter
from app.services.adapters.douban import DoubanAdapter


class FriendSyncAdapter(SourceAdapter):
    seen_friend_cookie = []
    history_calls = []

    def fetch_friend_usernames(self, username, cookie, max_count=20):
        FriendSyncAdapter.seen_friend_cookie.append((username, cookie, max_count))
        return ["friend_a", "friend_b"][:max_count]

    def fetch_history(self, username, cookie, page_cursor, media_type):
        FriendSyncAdapter.history_calls.append((username, cookie, page_cursor, media_type))
        if media_type != "book" or page_cursor > 0:
            return HistoryPage(records=[], next_cursor=None)
        return HistoryPage(
            records=[
                HistoryRecord(
                    subject_id=f"{username}_book_1",
                    title=f"{username} Book",
                    type="book",
                    year=2020,
                    douban_url=f"https://book.douban.com/subject/{username}_book_1/",
                    rating=8.0,
                    interacted_at=datetime(2025, 1, 1),
                )
            ],
            next_cursor=None,
        )

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return [
            CandidateItem(
                subject_id="new_book_1",
                title="New Book",
                type="book",
                year=2024,
                douban_url="https://book.douban.com/subject/new_book_1/",
                score=0.9,
            )
        ]


class CookieFallbackFriendAdapter(SourceAdapter):
    seen_friend_cookie = []
    history_calls = []

    def _detect_cookie_username(self, cookie):
        return "205927986"

    def fetch_friend_usernames(self, username, cookie, max_count=20):
        CookieFallbackFriendAdapter.seen_friend_cookie.append((username, cookie, max_count))
        if username == "demo_user":
            return []
        if username == "205927986":
            return ["friend_cookie"][:max_count]
        return []

    def fetch_history(self, username, cookie, page_cursor, media_type):
        CookieFallbackFriendAdapter.history_calls.append((username, cookie, page_cursor, media_type))
        if media_type != "book" or page_cursor > 0:
            return HistoryPage(records=[], next_cursor=None)
        return HistoryPage(
            records=[
                HistoryRecord(
                    subject_id=f"{username}_book_1",
                    title=f"{username} Book",
                    type="book",
                    year=2020,
                    douban_url=f"https://book.douban.com/subject/{username}_book_1/",
                    rating=8.0,
                    interacted_at=datetime(2025, 1, 1),
                )
            ],
            next_cursor=None,
        )

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return []


class AntiBotFriendAdapter(SourceAdapter):
    def fetch_friend_usernames(self, username, cookie, max_count=20):
        raise RuntimeError(
            "Douban contacts was blocked by anti-bot. Please wait and retry, or manually paste friend usernames/URLs."
        )

    def fetch_history(self, username, cookie, page_cursor, media_type):
        if media_type != "book" or page_cursor > 0:
            return HistoryPage(records=[], next_cursor=None)
        return HistoryPage(
            records=[
                HistoryRecord(
                    subject_id=f"{username}_book_1",
                    title=f"{username} Book",
                    type="book",
                    year=2020,
                    douban_url=f"https://book.douban.com/subject/{username}_book_1/",
                    rating=8.0,
                    interacted_at=datetime(2025, 1, 1),
                )
            ],
            next_cursor=None,
        )

    def fetch_candidate_pool(self, seed_items, cookie=None):
        return []


def test_friend_sync_endpoint_discovers_and_syncs_friends(client, db_session, monkeypatch):
    from app.services.cookie_capture import cookie_capture_manager

    FriendSyncAdapter.seen_friend_cookie = []
    FriendSyncAdapter.history_calls = []
    cookie_capture_manager.set_cookie("douban", "dbcl2=abc123; ck=xyz")

    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FriendSyncAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FriendSyncAdapter())
    monkeypatch.setattr("app.routers.sync.get_source_adapter", lambda source: FriendSyncAdapter())

    # Ensure owner exists in local DB first.
    first = client.post(
        "/api/sync",
        json={"source": "douban", "username": "demo_user", "cookie": None, "force_full": False, "sync_scope": "book"},
    )
    assert first.status_code == 200

    response = client.post(
        "/api/friends/sync",
        json={
            "source": "douban",
            "username": "demo_user",
            "cookie": None,
            "force_full": False,
            "sync_scope": "book",
            "max_friends": 10,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["owner_username"] == "demo_user"
    assert payload["total_friends"] == 2
    assert payload["friend_usernames"] == ["friend_a", "friend_b"]
    assert payload["friend_profiles"] == [
        {
            "username": "friend_a",
            "display_name": "friend_a",
            "profile_url": "https://www.douban.com/people/friend_a/",
        },
        {
            "username": "friend_b",
            "display_name": "friend_b",
            "profile_url": "https://www.douban.com/people/friend_b/",
        },
    ]
    assert len(payload["job_ids"]) == 2

    # Cookie must be reused for discovering/syncing friends.
    assert FriendSyncAdapter.seen_friend_cookie
    assert FriendSyncAdapter.seen_friend_cookie[0][1] == "dbcl2=abc123; ck=xyz"
    assert any(call[0] == "friend_a" and call[1] == "dbcl2=abc123; ck=xyz" for call in FriendSyncAdapter.history_calls)

    friend_a = db_session.exec(select(User).where(User.source == "douban", User.username == "friend_a")).first()
    friend_b = db_session.exec(select(User).where(User.source == "douban", User.username == "friend_b")).first()
    assert friend_a is not None
    assert friend_b is not None


def test_friend_sync_endpoint_falls_back_to_cookie_identity(client, db_session, monkeypatch):
    from app.services.cookie_capture import cookie_capture_manager

    CookieFallbackFriendAdapter.seen_friend_cookie = []
    CookieFallbackFriendAdapter.history_calls = []
    cookie_capture_manager.set_cookie("douban", "dbcl2=205927986:token; ck=xyz")

    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: CookieFallbackFriendAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: CookieFallbackFriendAdapter())
    monkeypatch.setattr("app.routers.sync.get_source_adapter", lambda source: CookieFallbackFriendAdapter())

    response = client.post(
        "/api/friends/sync",
        json={
            "source": "douban",
            "username": "demo_user",
            "cookie": None,
            "force_full": False,
            "sync_scope": "book",
            "max_friends": 10,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["owner_username"] == "205927986"
    assert payload["friend_usernames"] == ["friend_cookie"]
    assert payload["friend_profiles"] == [
        {
            "username": "friend_cookie",
            "display_name": "friend_cookie",
            "profile_url": "https://www.douban.com/people/friend_cookie/",
        }
    ]
    assert payload["total_friends"] == 1
    assert len(payload["job_ids"]) == 1

    # First try uses provided username, then falls back to cookie identity.
    assert CookieFallbackFriendAdapter.seen_friend_cookie[0][0] == "demo_user"
    assert CookieFallbackFriendAdapter.seen_friend_cookie[1][0] == "205927986"
    assert any(
        call[0] == "friend_cookie" and call[1] == "dbcl2=205927986:token; ck=xyz"
        for call in CookieFallbackFriendAdapter.history_calls
    )

    friend = db_session.exec(select(User).where(User.source == "douban", User.username == "friend_cookie")).first()
    assert friend is not None


def test_friend_sync_endpoint_returns_local_profiles_when_antibot(client, monkeypatch):
    monkeypatch.setattr("app.services.adapters.get_source_adapter", lambda source: FriendSyncAdapter())
    monkeypatch.setattr("app.tasks.job_runner.get_source_adapter", lambda source: FriendSyncAdapter())

    for username in ("demo_user", "friend_a", "friend_b"):
        response = client.post(
            "/api/sync",
            json={
                "source": "douban",
                "username": username,
                "cookie": None,
                "force_full": False,
                "sync_scope": "book",
            },
        )
        assert response.status_code == 200

    monkeypatch.setattr("app.routers.sync.get_source_adapter", lambda source: AntiBotFriendAdapter())

    response = client.post(
        "/api/friends/sync",
        json={
            "source": "douban",
            "username": "demo_user",
            "cookie": None,
            "force_full": False,
            "sync_scope": "book",
            "max_friends": 10,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "local_only"
    assert payload["owner_username"] == "demo_user"
    assert payload["total_friends"] == 2
    assert sorted(payload["friend_usernames"]) == ["friend_a", "friend_b"]
    assert payload["job_ids"] == []
    assert {profile["username"] for profile in payload["friend_profiles"]} == {"friend_a", "friend_b"}


class FakeResponse:
    def __init__(self, status_code: int, text: str, url: str):
        self.status_code = status_code
        self.text = text
        self.url = url


class ContactsClient:
    def get(self, url, params=None, headers=None):
        if url == "https://www.douban.com/people/demo_user/contacts" and params and params.get("start") == 70:
            html = """
            <html><body>
              <a href="/people/friend_3/" title="好友三">friend3</a>
            </body></html>
            """
            return FakeResponse(
                200,
                html,
                "https://www.douban.com/people/demo_user/contacts?start=70",
            )
        if url == "https://www.douban.com/people/demo_user/contacts":
            html = """
            <html><body>
              <a href="https://www.douban.com/people/friend_1/" title="好友一">friend1</a>
              <a href="/people/friend_2/" title="好友二">friend2</a>
              <a href="/people/demo_user/">self</a>
              <span class="next"><a href="https://www.douban.com/people/demo_user/contacts?start=70">next</a></span>
            </body></html>
            """
            return FakeResponse(200, html, "https://www.douban.com/people/demo_user/contacts")
        return FakeResponse(404, "<html>not found</html>", "https://www.douban.com/404")


def test_douban_adapter_fetch_friend_usernames_parses_contacts_pages():
    adapter = DoubanAdapter(client=ContactsClient())
    names = adapter.fetch_friend_usernames("demo_user", cookie="dbcl2=abc; ck=xyz", max_count=10)
    assert names == ["friend_1", "friend_2", "friend_3"]


def test_douban_adapter_fetch_friend_profiles_parses_display_name():
    adapter = DoubanAdapter(client=ContactsClient())
    profiles = adapter.fetch_friend_profiles("demo_user", cookie="dbcl2=abc; ck=xyz", max_count=10)
    assert profiles == [
        {
            "username": "friend_1",
            "display_name": "好友一",
            "profile_url": "https://www.douban.com/people/friend_1/",
        },
        {
            "username": "friend_2",
            "display_name": "好友二",
            "profile_url": "https://www.douban.com/people/friend_2/",
        },
        {
            "username": "friend_3",
            "display_name": "好友三",
            "profile_url": "https://www.douban.com/people/friend_3/",
        },
    ]


class Contacts403Client:
    def get(self, url, params=None, headers=None):
        return FakeResponse(
            403,
            "<html><title>豆瓣 - 登录跳转页</title></html>",
            "https://sec.douban.com/b?r=https%3A%2F%2Fwww.douban.com%2Fcontacts%2Flist",
        )


def test_douban_adapter_fetch_friend_usernames_uses_curl_fallback_on_403(monkeypatch):
    adapter = DoubanAdapter(client=Contacts403Client())
    monkeypatch.setattr(
        adapter,
        "_fetch_contacts_via_curl",
        lambda username, cookie, start, target_url=None: (
            '<html><body><a href="/people/friend_10/">f10</a>'
            '<a href="https://www.douban.com/people/friend_20/">f20</a></body></html>'
        ),
    )
    names = adapter.fetch_friend_usernames("demo_user", cookie="dbcl2=abc; ck=xyz", max_count=10)
    assert names == ["friend_10", "friend_20"]


class ContactsBlockedClient:
    def get(self, url, params=None, headers=None):
        return FakeResponse(
            200,
            "<html><head><title>禁止访问</title></head><body><a href=\"/accounts/login\">登录</a></body></html>",
            "https://www.douban.com/misc/sorry?original-url=https%3A%2F%2Fwww.douban.com%2Fpeople%2Fdemo_user%2Fcontacts",
        )


def test_douban_adapter_fetch_friend_usernames_reports_antibot_instead_of_login():
    adapter = DoubanAdapter(client=ContactsBlockedClient())
    try:
        adapter.fetch_friend_usernames("demo_user", cookie="dbcl2=abc; ck=xyz", max_count=10)
        assert False, "expected anti-bot RuntimeError"
    except RuntimeError as exc:
        text = str(exc)
        assert "anti-bot" in text
        assert "requires login" not in text


class ContactsListPaginationClient:
    def get(self, url, params=None, headers=None):
        if url == "https://www.douban.com/contacts/list?tag=0&start=20":
            html = """
            <html><body>
              <a href="/people/friend_3/">friend3</a>
              <a href="/people/friend_4/">friend4</a>
            </body></html>
            """
            return FakeResponse(200, html, "https://www.douban.com/contacts/list?tag=0&start=20")
        if url == "https://www.douban.com/people/demo_user/contacts":
            html = """
            <html><body>
              <a href="/people/friend_1/">friend1</a>
              <a href="/people/friend_2/">friend2</a>
              <span class="next"><a href="/contacts/list?tag=0&start=20">next</a></span>
            </body></html>
            """
            return FakeResponse(200, html, "https://www.douban.com/people/demo_user/contacts")
        return FakeResponse(404, "<html>not found</html>", "https://www.douban.com/404")


def test_douban_adapter_fetch_friend_usernames_supports_contacts_list_pagination():
    adapter = DoubanAdapter(client=ContactsListPaginationClient())
    names = adapter.fetch_friend_usernames("demo_user", cookie="dbcl2=abc; ck=xyz", max_count=10)
    assert names == ["friend_1", "friend_2", "friend_3", "friend_4"]


class PeopleBlockedClient:
    def get(self, url, params=None, headers=None):
        return FakeResponse(
            200,
            "<html><head><title>禁止访问</title></head><body>异常请求</body></html>",
            "https://www.douban.com/misc/sorry?original-url=https%3A%2F%2Fbook.douban.com%2Fpeople%2Ffriend_a%2Fcollect",
        )


def test_douban_adapter_fetch_history_uses_curl_fallback_on_antibot(monkeypatch):
    adapter = DoubanAdapter(client=PeopleBlockedClient())
    monkeypatch.setattr(
        adapter,
        "_fetch_page_via_curl",
        lambda cookie, target_url, referer: (
            '<html><body><li class="item">'
            '<a href="https://book.douban.com/subject/1234567/">孤島的來訪者</a>'
            '<span class="rating5-t"></span><span class="date">2025-01-02</span>'
            "</li></body></html>"
        ),
    )

    page = adapter.fetch_history(
        username="friend_a",
        cookie="dbcl2=abc; ck=xyz",
        page_cursor=0,
        media_type="book",
    )
    assert len(page.records) == 1
    assert page.records[0].subject_id == "1234567"
    assert page.records[0].title == "孤島的來訪者"
