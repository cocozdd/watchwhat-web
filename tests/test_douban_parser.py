from pathlib import Path

from app.services.douban_parser import parse_history_page


def test_parse_movie_tv_history_page():
    html = Path("tests/fixtures/douban_movie_page1.html").read_text(encoding="utf-8")

    page = parse_history_page(html, media_type="movie_tv", current_cursor=0)

    assert len(page.records) == 2
    assert page.next_cursor == 15
    assert page.records[0].subject_id == "1000001"
    assert page.records[0].rating == 10.0
    assert page.records[0].type == "movie"
    assert page.records[1].subject_id == "1000002"
    assert page.records[1].type == "tv"


def test_parse_book_history_page():
    html = Path("tests/fixtures/douban_book_page1.html").read_text(encoding="utf-8")

    page = parse_history_page(html, media_type="book", current_cursor=0)

    assert len(page.records) == 1
    assert page.next_cursor is None
    assert page.records[0].subject_id == "2000001"
    assert page.records[0].type == "book"
    assert page.records[0].rating == 10.0
