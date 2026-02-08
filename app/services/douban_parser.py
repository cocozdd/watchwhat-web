import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.services.adapters.base import CandidateItem, HistoryPage, HistoryRecord

SUBJECT_RE = re.compile(r"/subject/(\d+)/")
RATING_RE = re.compile(r"rating([1-5])-t")
YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")
START_RE = re.compile(r"[?&]start=(\d+)")
DATE_RE = re.compile(r"(20\d{2}-\d{1,2}-\d{1,2})")


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _parse_subject_id(url: str) -> Optional[str]:
    match = SUBJECT_RE.search(url)
    return match.group(1) if match else None


def _parse_rating(node) -> Optional[float]:
    for span in node.select("span"):
        classes = span.get("class", [])
        for class_name in classes:
            rating_match = RATING_RE.search(class_name)
            if rating_match:
                return float(int(rating_match.group(1)) * 2)
    return None


def _parse_date(raw: str) -> Optional[datetime]:
    value = raw.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _extract_year(text: str) -> Optional[int]:
    year_match = YEAR_RE.search(text)
    if not year_match:
        return None
    return int(year_match.group(1))


def _extract_start(url: str) -> Optional[int]:
    match = START_RE.search(url)
    if not match:
        return None
    return int(match.group(1))


def _guess_movie_or_tv(text: str) -> str:
    lower = text.lower()
    if "电视剧" in text or "tv" in lower or "季" in text or "集" in text:
        return "tv"
    return "movie"


def _find_block(link):
    node = link
    depth = 0
    while node is not None and depth < 8:
        classes = " ".join(node.get("class", [])) if hasattr(node, "get") else ""
        if getattr(node, "name", None) in {"li", "div"} and (
            "item" in classes or "subject" in classes or "interest" in classes
        ):
            return node
        node = getattr(node, "parent", None)
        depth += 1
    return getattr(link, "parent", None)


def _extract_date_from_text(text: str) -> Optional[datetime]:
    match = DATE_RE.search(text)
    if not match:
        return None
    return _parse_date(match.group(1))


def _is_collection_context(soup: BeautifulSoup) -> bool:
    text = soup.get_text(" ", strip=True).lower()
    collection_markers = ["看过", "读过", "听过", "collect", "我的", "/mine"]
    for marker in collection_markers:
        if marker in text:
            return True
    if soup.select(".item") or soup.select(".interest-list") or soup.select(".grid-view"):
        return True
    return False


def _parse_generic_records(soup: BeautifulSoup, media_type: str) -> List[HistoryRecord]:
    if not _is_collection_context(soup):
        return []

    records: List[HistoryRecord] = []
    seen = set()
    for link in soup.select("a[href*='/subject/']"):
        href = link.get("href", "")
        subject_id = _parse_subject_id(href)
        if not subject_id or subject_id in seen:
            continue
        seen.add(subject_id)

        block = _find_block(link)
        text_blob = _clean_text(block.get_text(" ", strip=True) if block else link.get_text(" ", strip=True))
        rating = _parse_rating(block or link)
        interacted_at = _extract_date_from_text(text_blob)

        if rating is None and interacted_at is None:
            continue

        if media_type == "book":
            item_type = "book"
        else:
            item_type = _guess_movie_or_tv(text_blob)

        title = _clean_text(link.get_text(" ", strip=True))
        if not title:
            continue

        records.append(
            HistoryRecord(
                subject_id=subject_id,
                title=title,
                type=item_type,
                year=_extract_year(text_blob),
                douban_url=href,
                rating=rating,
                interacted_at=interacted_at,
                comment=None,
                tags=[],
                metadata={"raw_text": text_blob},
            )
        )
    return records


def _detect_next_cursor(soup: BeautifulSoup, current_cursor: int) -> Optional[int]:
    next_link = soup.select_one("span.next a[href]")
    if next_link:
        candidate = _extract_start(next_link.get("href", ""))
        if candidate is not None:
            return candidate

    candidates = []
    for link in soup.select("a[href*='start=']"):
        val = _extract_start(link.get("href", ""))
        if val is not None and val > current_cursor:
            candidates.append(val)
    if candidates:
        return min(candidates)
    return None


def parse_history_page(html: str, media_type: str, current_cursor: int = 0) -> HistoryPage:
    soup = BeautifulSoup(html, "html.parser")
    records: List[HistoryRecord] = []

    for item in soup.select("li.item, li.subject-item"):
        link = item.select_one("a[href*='/subject/']")
        if not link:
            continue

        href = link.get("href", "")
        subject_id = _parse_subject_id(href)
        if not subject_id:
            continue

        title_node = item.select_one("h2 a[href*='/subject/']")
        title = _clean_text((title_node or link).get("title", "") or (title_node or link).get_text(" ", strip=True))
        text_blob = _clean_text(item.get_text(" ", strip=True))
        rating = _parse_rating(item)

        date_node = item.select_one("span.date")
        date_text = date_node.get_text(strip=True) if date_node else ""
        date_text = DATE_RE.search(date_text).group(1) if DATE_RE.search(date_text) else date_text
        interacted_at = _parse_date(date_text)

        comment_node = item.select_one("span.comment, p.comment")
        comment = comment_node.get_text(strip=True) if comment_node else None
        if comment == "":
            comment = None

        tags_node = item.select_one("span.tags")
        tags = []
        if tags_node:
            tags = [x for x in _clean_text(tags_node.get_text(" ", strip=True)).split(" ") if x]

        if media_type == "book":
            item_type = "book"
        else:
            item_type = _guess_movie_or_tv(text_blob)

        records.append(
            HistoryRecord(
                subject_id=subject_id,
                title=title,
                type=item_type,
                year=_extract_year(text_blob),
                douban_url=href,
                rating=rating,
                interacted_at=interacted_at,
                comment=comment,
                tags=tags,
                metadata={"raw_text": text_blob},
            )
        )

    if not records:
        records = _parse_generic_records(soup, media_type)

    next_cursor = _detect_next_cursor(soup, current_cursor)
    if next_cursor is None and len(records) >= 15:
        next_cursor = current_cursor + 15

    return HistoryPage(records=records, next_cursor=next_cursor)


def parse_subject_candidates(html: str, default_type: str) -> List[CandidateItem]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[CandidateItem] = []
    seen = set()

    for link in soup.select("a[href*='/subject/']"):
        href = link.get("href", "")
        subject_id = _parse_subject_id(href)
        if not subject_id or subject_id in seen:
            continue
        seen.add(subject_id)

        title = _clean_text(link.get_text(" ", strip=True))
        if not title:
            continue

        full_url = urljoin("https://movie.douban.com", href)
        item_type = "book" if "book.douban.com" in full_url else default_type

        results.append(
            CandidateItem(
                subject_id=subject_id,
                title=title,
                type=item_type,
                year=_extract_year(title),
                douban_url=full_url,
                score=0.5,
            )
        )

        if len(results) >= 60:
            break

    return results


def parse_top250_page(html: str, default_type: str) -> List[CandidateItem]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[CandidateItem] = []

    for item in soup.select("li .title"):
        link = item.find_parent("a") if item.name != "a" else item
        if link is None:
            link = item.parent if getattr(item.parent, "name", None) == "a" else None
        if link is None:
            continue

        href = link.get("href", "")
        subject_id = _parse_subject_id(href)
        if not subject_id:
            continue

        title = _clean_text(item.get_text(" ", strip=True))
        if not title:
            continue

        results.append(
            CandidateItem(
                subject_id=subject_id,
                title=title,
                type=default_type,
                year=_extract_year(title),
                douban_url=href,
                score=0.4,
            )
        )

    return results
