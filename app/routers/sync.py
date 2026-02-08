from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import func

from app.db import get_engine
from app.models import Interaction, Item, SyncJob, User
from app.schemas import (
    CookieCaptureStartRequest,
    CookieCaptureStatusResponse,
    FriendProfile,
    FriendsSyncRequest,
    FriendsSyncResponse,
    LibraryItem,
    LibraryResponse,
    SyncRequest,
    SyncStartResponse,
    SyncStatusResponse,
)
from app.services.adapters import get_source_adapter
from app.services.cookie_capture import cookie_capture_manager
from app.services.douban_username import infer_sync_media_types, normalize_douban_username
from app.tasks.job_runner import sync_job_runner

router = APIRouter(tags=["sync"])


def _resolve_sync_media_types(sync_scope: str, raw_username: str, normalized_username: str) -> list:
    if sync_scope == "book":
        return ["book"]
    if sync_scope == "movie_tv":
        return ["movie_tv"]
    if sync_scope == "all":
        return ["movie_tv", "book"]
    return infer_sync_media_types(raw_username, normalized_username)


def _detect_cookie_username(source: str, cookie: str) -> str:
    if not cookie:
        return ""
    try:
        adapter = get_source_adapter(source)
        detector = getattr(adapter, "_detect_cookie_username", None)
        if callable(detector):
            detected = detector(cookie)
            if isinstance(detected, str) and detected.strip():
                return detected.strip()
    except Exception:
        return ""
    return ""


def _resolve_username_from_cookie(source: str, normalized_username: str, cookie: str) -> str:
    """Resolve username from cookie only when no valid username was provided.

    When the user provides a valid username (e.g. 'cocodzh'), keep it as-is.
    The 404 fallback in the adapter handles wrong usernames at fetch time.
    """
    if not cookie or normalized_username == "__mine__":
        return normalized_username
    if normalized_username:
        return normalized_username
    detected = _detect_cookie_username(source, cookie)
    if detected:
        return detected
    return normalized_username


def _is_antibot_error_message(message: str) -> bool:
    text = (message or "").lower()
    return "anti-bot" in text or "禁止访问" in message or "风控" in message or "misc/sorry" in text


def _load_local_friend_profiles(
    session: Session,
    source: str,
    owner_username: str,
    max_friends: int,
) -> list[FriendProfile]:
    stmt = (
        select(User.username, func.count(Interaction.id).label("interaction_count"))
        .join(Interaction, Interaction.user_id == User.id)
        .where(User.source == source, User.username != owner_username)
        .group_by(User.id)
        .order_by(func.count(Interaction.id).desc(), User.last_synced_at.desc())
        .limit(max_friends)
    )
    rows = session.exec(stmt).all()
    profiles: list[FriendProfile] = []
    seen = set()
    for row in rows:
        username = (row[0] or "").strip()
        if not username or username in seen:
            continue
        seen.add(username)
        profiles.append(
            FriendProfile(
                username=username,
                display_name=username,
                profile_url=f"https://www.douban.com/people/{username}/",
            )
        )
    return profiles


@router.post("/sync", response_model=SyncStartResponse)
def start_sync(request: SyncRequest) -> SyncStartResponse:
    if request.source != "douban":
        raise HTTPException(status_code=400, detail="Only douban source is supported in v1")

    if request.cookie:
        cookie_capture_manager.set_cookie(request.source, request.cookie)
    cookie = request.cookie or cookie_capture_manager.get_cookie(request.source)
    normalized_username = normalize_douban_username(request.username)
    if normalized_username == "__mine__" and not cookie:
        raise HTTPException(
            status_code=400,
            detail="Mine-page sync requires login cookie. Please capture cookie first.",
        )
    if not normalized_username:
        raise HTTPException(
            status_code=400,
            detail="Invalid Douban username. Please provide a username or profile URL with /people/<username>/.",
        )
    effective_username = _resolve_username_from_cookie(
        source=request.source,
        normalized_username=normalized_username,
        cookie=cookie or "",
    )

    media_types = _resolve_sync_media_types(request.sync_scope, request.username, normalized_username)
    job_id = sync_job_runner.start_sync(
        source=request.source,
        username=effective_username,
        cookie=cookie,
        force_full=request.force_full,
        media_types=media_types,
    )
    return SyncStartResponse(job_id=job_id, status="queued")


@router.post("/friends/sync", response_model=FriendsSyncResponse)
def sync_friends(request: FriendsSyncRequest) -> FriendsSyncResponse:
    if request.source != "douban":
        raise HTTPException(status_code=400, detail="Only douban source is supported in v1")

    if request.cookie:
        cookie_capture_manager.set_cookie(request.source, request.cookie)
    cookie = request.cookie or cookie_capture_manager.get_cookie(request.source)

    normalized_username = normalize_douban_username(request.username)
    if normalized_username == "__mine__" and not cookie:
        raise HTTPException(
            status_code=400,
            detail="Mine-page friend sync requires login cookie. Please capture cookie first.",
        )
    if not normalized_username:
        raise HTTPException(
            status_code=400,
            detail="Invalid Douban username. Please provide a username or profile URL with /people/<username>/.",
        )

    effective_username = _resolve_username_from_cookie(
        source=request.source,
        normalized_username=normalized_username,
        cookie=cookie or "",
    )
    adapter = get_source_adapter(request.source)
    profile_fetcher = getattr(adapter, "fetch_friend_profiles", None)
    fetcher = getattr(adapter, "fetch_friend_usernames", None)
    if not callable(profile_fetcher) and not callable(fetcher):
        raise HTTPException(status_code=400, detail="Current source adapter does not support friend discovery")

    def _discover_for(owner_username: str) -> list[FriendProfile]:
        if callable(profile_fetcher):
            raw_profiles = profile_fetcher(owner_username, cookie, request.max_friends)
            profiles: list[FriendProfile] = []
            for raw in raw_profiles or []:
                username = (raw.get("username") if isinstance(raw, dict) else "") or ""
                compact = username.strip()
                if not compact:
                    continue
                display_name = (raw.get("display_name") if isinstance(raw, dict) else "") or compact
                profile_url = (raw.get("profile_url") if isinstance(raw, dict) else "") or (
                    f"https://www.douban.com/people/{compact}/"
                )
                profiles.append(
                    FriendProfile(
                        username=compact,
                        display_name=str(display_name).strip() or compact,
                        profile_url=str(profile_url).strip() or f"https://www.douban.com/people/{compact}/",
                    )
                )
            return profiles

        raw_usernames = fetcher(owner_username, cookie, request.max_friends)
        profiles = []
        for raw_username in raw_usernames or []:
            compact = (raw_username or "").strip()
            if not compact:
                continue
            profiles.append(
                FriendProfile(
                    username=compact,
                    display_name=compact,
                    profile_url=f"https://www.douban.com/people/{compact}/",
                )
            )
        return profiles

    try:
        discovered_profiles = _discover_for(effective_username)
    except Exception as exc:
        if _is_antibot_error_message(str(exc)):
            with Session(get_engine()) as session:
                local_profiles = _load_local_friend_profiles(
                    session=session,
                    source=request.source,
                    owner_username=effective_username,
                    max_friends=request.max_friends,
                )
            if local_profiles:
                friend_usernames = [p.username for p in local_profiles]
                return FriendsSyncResponse(
                    status="local_only",
                    owner_username=effective_username,
                    total_friends=len(friend_usernames),
                    friend_usernames=friend_usernames,
                    friend_profiles=local_profiles,
                    job_ids=[],
                )
        raise HTTPException(status_code=400, detail=f"Failed to fetch friend list: {exc}") from exc

    cookie_identity = _detect_cookie_username(request.source, cookie or "")
    if not discovered_profiles and cookie_identity and cookie_identity != effective_username:
        try:
            fallback_profiles = _discover_for(cookie_identity)
            if fallback_profiles:
                effective_username = cookie_identity
                discovered_profiles = fallback_profiles
        except Exception:
            # Keep original empty-result behavior when fallback is unavailable.
            pass

    friend_profiles: list[FriendProfile] = []
    friend_usernames = []
    seen = {effective_username}
    for profile in discovered_profiles:
        compact = (profile.username or "").strip()
        if not compact or compact in seen:
            continue
        seen.add(compact)
        friend_usernames.append(compact)
        friend_profiles.append(
            FriendProfile(
                username=compact,
                display_name=(profile.display_name or compact).strip() or compact,
                profile_url=(profile.profile_url or f"https://www.douban.com/people/{compact}/").strip(),
            )
        )

    media_types = _resolve_sync_media_types(request.sync_scope, request.username, normalized_username)
    job_ids = []
    for friend_username in friend_usernames:
        job_id = sync_job_runner.start_sync(
            source=request.source,
            username=friend_username,
            cookie=cookie,
            force_full=request.force_full,
            media_types=media_types,
        )
        job_ids.append(job_id)

    return FriendsSyncResponse(
        status="queued",
        owner_username=effective_username,
        total_friends=len(friend_usernames),
        friend_usernames=friend_usernames,
        friend_profiles=friend_profiles,
        job_ids=job_ids,
    )


@router.get("/sync/{job_id}", response_model=SyncStatusResponse)
def get_sync_status(job_id: str) -> SyncStatusResponse:
    with Session(get_engine()) as session:
        job = session.get(SyncJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        user = session.get(User, job.user_id)

        counts = sync_job_runner.get_job_counts(job_id)
        return SyncStatusResponse(
            status=job.status,
            done=job.done,
            total=job.total,
            message=job.message if job.message else (job.error_message or ""),
            effective_username=user.username if user else None,
            counts=counts,
            added_preview=sync_job_runner.get_job_added_preview(job_id),
        )


@router.get("/library", response_model=LibraryResponse)
def get_library(
    source: str = Query(default="douban"),
    username: str = Query(...),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> LibraryResponse:
    if source != "douban":
        raise HTTPException(status_code=400, detail="Only douban source is supported in v1")

    normalized_username = normalize_douban_username(username)
    if not normalized_username:
        raise HTTPException(
            status_code=400,
            detail="Invalid Douban username. Please provide a username or profile URL with /people/<username>/.",
        )

    with Session(get_engine()) as session:
        user = session.exec(
            select(User).where(
                User.source == source,
                User.username == normalized_username,
            )
        ).first()

        has_data = user is not None and session.exec(
            select(Interaction).where(Interaction.user_id == user.id).limit(1)
        ).first() is not None
        if not has_data:
            cookie = cookie_capture_manager.get_cookie(source)
            if cookie:
                try:
                    adapter = get_source_adapter(source)
                    detected = adapter._detect_cookie_username(cookie)
                    if detected and detected != normalized_username:
                        alt_user = session.exec(
                            select(User).where(
                                User.source == source,
                                User.username == detected,
                            )
                        ).first()
                        if alt_user is not None:
                            user = alt_user
                            normalized_username = detected
                except Exception:
                    pass

        if user is None:
            raise HTTPException(status_code=404, detail="User has no synced data. Please sync first.")

        rows = session.exec(
            select(Interaction, Item)
            .join(Item, Interaction.item_id == Item.id)
            .where(Interaction.user_id == user.id)
        ).all()

    ordered = sorted(
        rows,
        key=lambda row: (
            row[0].interacted_at or datetime.min,
            row[0].created_at or datetime.min,
        ),
        reverse=True,
    )
    movie_tv_count = sum(1 for _, item in ordered if item.type in {"movie", "tv"})
    book_count = sum(1 for _, item in ordered if item.type == "book")
    sliced = ordered[offset : offset + limit]

    return LibraryResponse(
        source=source,
        username=normalized_username,
        total=len(ordered),
        movie_tv_count=movie_tv_count,
        book_count=book_count,
        items=[
            LibraryItem(
                subject_id=item.subject_id,
                title=item.title,
                type=item.type,
                year=item.year,
                douban_url=item.douban_url,
                rating=interaction.rating,
                interacted_at=interaction.interacted_at,
            )
            for interaction, item in sliced
        ],
    )


@router.get("/cookie/status")
def get_cookie_status(source: str = Query(default="douban")) -> dict:
    cookie = cookie_capture_manager.get_cookie(source)
    has_cookie = bool(cookie)
    has_login = False
    if has_cookie:
        from app.services.cookie_capture import has_login_cookie
        names = [p.split("=", 1)[0].strip() for p in cookie.split(";") if "=" in p]
        has_login = has_login_cookie(names)
    return {"has_cookie": has_cookie, "has_login_cookie": has_login}


@router.post("/cookie/auto/start", response_model=CookieCaptureStatusResponse)
def start_cookie_auto_capture(request: CookieCaptureStartRequest) -> CookieCaptureStatusResponse:
    if request.source != "douban":
        raise HTTPException(status_code=400, detail="Only douban source is supported in v1")
    status = cookie_capture_manager.start_auto_capture(request.source)
    return CookieCaptureStatusResponse(
        job_id=status.job_id,
        status=status.status,
        message=status.message,
        has_cookie=status.has_cookie,
    )


@router.get("/cookie/auto/{job_id}", response_model=CookieCaptureStatusResponse)
def get_cookie_auto_capture_status(job_id: str) -> CookieCaptureStatusResponse:
    try:
        status = cookie_capture_manager.get_capture_status(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="cookie capture job not found") from exc

    return CookieCaptureStatusResponse(
        job_id=status.job_id,
        status=status.status,
        message=status.message,
        has_cookie=status.has_cookie,
    )
