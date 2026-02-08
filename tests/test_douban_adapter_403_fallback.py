from app.services.adapters.douban import DoubanAdapter


class FakeResponse:
    def __init__(self, status_code, text, url="https://example.com"):
        self.status_code = status_code
        self.text = text
        self.url = url


class StubClient403Fallback:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))

        if url == "https://www.douban.com/people/99999/":
            return FakeResponse(200, '<html>profile</html>', url="https://www.douban.com/people/other_user/")

        if url == "https://movie.douban.com/people/cocodzh/collect":
            return FakeResponse(403, "forbidden")

        if url == "https://movie.douban.com/mine":
            return FakeResponse(
                200,
                '<html><body>看过<div class="item"><h2><a href="https://movie.douban.com/subject/1292052/">肖申克的救赎</a></h2><span class="rating5-t"></span><span>2025-01-01</span></div></body></html>',
                url="https://movie.douban.com/mine?status=collect",
            )

        raise AssertionError(f"Unexpected URL: {url}")


def test_fetch_history_403_falls_back_to_mine_when_cookie_present():
    adapter = DoubanAdapter(client=StubClient403Fallback())

    page = adapter.fetch_history(
        username="cocodzh",
        cookie='dbcl2="99999:token"; ck=xyz',
        page_cursor=0,
        media_type="movie_tv",
    )

    assert len(page.records) == 1
    assert page.records[0].subject_id == "1292052"


class StubClient403NoFallback:
    def get(self, url, params=None, headers=None):
        if url == "https://movie.douban.com/people/cocodzh/collect":
            return FakeResponse(403, "forbidden")
        if url == "https://movie.douban.com/mine":
            return FakeResponse(403, "forbidden")
        return FakeResponse(500, "x")


def test_fetch_history_403_without_working_mine_fallback_raises():
    adapter = DoubanAdapter(client=StubClient403NoFallback())
    try:
        adapter.fetch_history(
            username="cocodzh",
            cookie="dbcl2=abc; ck=xyz",
            page_cursor=0,
            media_type="movie_tv",
        )
    except RuntimeError as exc:
        assert "Douban fetch failed (403)" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
