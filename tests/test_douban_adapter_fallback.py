import pytest

from app.services.adapters.douban import DoubanAdapter


class FakeResponse:
    def __init__(self, status_code: int, text: str, url: str = "https://example.com"):
        self.status_code = status_code
        self.text = text
        self.url = url


class StubClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))

        if url == "https://www.douban.com/people/12345/":
            return FakeResponse(
                200, '<html>profile</html>',
                url="https://www.douban.com/people/right_user/",
            )

        if url == "https://movie.douban.com/people/wrong_user/collect":
            return FakeResponse(404, "<html><title>404</title></html>")

        if url == "https://movie.douban.com/people/right_user/collect":
            return FakeResponse(200, "<html><body><ul class='grid_view'></ul></body></html>")

        raise AssertionError(f"Unexpected URL: {url}")


def test_fetch_history_falls_back_to_cookie_account_when_username_is_wrong():
    client = StubClient()
    adapter = DoubanAdapter(client=client)

    page = adapter.fetch_history(
        username="wrong_user",
        cookie='dbcl2="12345:token"; ck=bbb',
        page_cursor=0,
        media_type="movie_tv",
    )

    assert page.records == []
    assert page.next_cursor is None

    called_urls = [c[0] for c in client.calls]
    assert "https://movie.douban.com/people/wrong_user/collect" in called_urls
    assert "https://www.douban.com/people/12345/" in called_urls
    assert "https://movie.douban.com/people/right_user/collect" in called_urls


def test_fetch_history_404_without_cookie_raises_helpful_error():
    class NoCookieClient:
        def get(self, url, params=None, headers=None):
            return FakeResponse(404, "<html><title>404</title></html>")

    adapter = DoubanAdapter(client=NoCookieClient())

    with pytest.raises(RuntimeError) as exc:
        adapter.fetch_history(
            username="wrong_user",
            cookie=None,
            page_cursor=0,
            media_type="movie_tv",
        )

    assert "Use the username from /people/<username>/" in str(exc.value)
