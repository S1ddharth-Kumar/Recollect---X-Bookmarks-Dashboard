from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bookmarks_organizer.config import Settings, get_settings
from bookmarks_organizer.db import Database
from bookmarks_organizer.embeddings import build_embedding_provider
from bookmarks_organizer.manual_import import ManualImportService
from bookmarks_organizer.models import SearchResult, TweetRecord
from bookmarks_organizer.scheduler import build_scheduler
from bookmarks_organizer.search import SearchService
from bookmarks_organizer.sync_service import BookmarkSyncService
from bookmarks_organizer.vector_store import SemanticIndex


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    db: Database
    search_service: SearchService
    sync_service: BookmarkSyncService
    import_service: ManualImportService
    templates: Jinja2Templates
    scheduler: object | None = None


def create_container() -> AppContainer:
    settings = get_settings()
    db = Database(settings.database_path)
    db.initialize()
    embedding_provider = build_embedding_provider(
        model_name=settings.embedding_model,
        fallback_dimension=settings.embedding_dimension,
    )
    semantic_index = SemanticIndex(db=db, prefer_faiss=settings.use_faiss)
    search_service = SearchService(
        db=db,
        embedding_provider=embedding_provider,
        semantic_index=semantic_index,
    )
    sync_service = BookmarkSyncService(
        db=db,
        search_service=search_service,
        browser_profile_dir=str(settings.browser_profile_dir),
        headless=settings.sync_headless,
        max_scrolls=settings.max_sync_scrolls,
        max_batch=settings.max_sync_batch,
        login_wait_seconds=settings.login_wait_seconds,
    )
    import_service = ManualImportService(db=db, search_service=search_service)
    templates = Jinja2Templates(directory=str(settings.templates_dir))
    return AppContainer(
        settings=settings,
        db=db,
        search_service=search_service,
        sync_service=sync_service,
        import_service=import_service,
        templates=templates,
    )


container = create_container()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    if container.settings.scheduler_enabled:
        scheduler = build_scheduler(
            container.sync_service,
            day_of_week=container.settings.scheduler_day_of_week,
            hour=container.settings.scheduler_hour,
            minute=container.settings.scheduler_minute,
        )
        scheduler.start()
    container.scheduler = scheduler
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title=container.settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(container.settings.static_dir)), name="static")

DEFAULT_RECENT_LIMIT = 10
DEFAULT_PAGE_SIZE = 20


def _format_saved_at(value: datetime | None) -> str:
    if value is None:
        return "Saved recently"
    return value.strftime("%b %d, %Y")


def _serialize_tweet(tweet: TweetRecord, *, source: str | None = None, score: float | None = None) -> dict[str, object]:
    preview_image = None
    if tweet.image_urls:
        preview_image = tweet.image_urls[0]
    elif tweet.video_poster_urls:
        preview_image = tweet.video_poster_urls[0]

    media_label = None
    if tweet.image_urls:
        total = len(tweet.image_urls)
        media_label = f"{total} image" if total == 1 else f"{total} images"
    elif tweet.video_urls or tweet.video_poster_urls:
        media_label = "Video"

    return {
        "tweet_id": tweet.tweet_id,
        "author": tweet.author,
        "handle": tweet.handle,
        "text": tweet.text,
        "url": tweet.url,
        "category": tweet.category,
        "tags": tweet.tags,
        "preview_image": preview_image,
        "media_label": media_label,
        "saved_at": _format_saved_at(tweet.bookmarked_at or tweet.created_at),
        "source": source,
        "score": f"{score:.3f}" if score is not None else None,
    }


def _serialize_search_results(results: list[SearchResult]) -> list[dict[str, object]]:
    return [
        _serialize_tweet(result.tweet, source=result.source, score=result.score)
        for result in results
    ]


def _serialize_bookmarks(bookmarks: list[TweetRecord]) -> list[dict[str, object]]:
    return [_serialize_tweet(tweet) for tweet in bookmarks]


def _page_url(request: Request, page: int) -> str:
    return str(request.url.include_query_params(page=page))


def _template_context(request: Request, **kwargs: object) -> dict[str, object]:
    base_context = {
        "request": request,
        "app_name": container.settings.app_name,
        "collections": container.db.list_collections(),
        "category_counts": container.db.get_category_counts(),
    }
    base_context.update(kwargs)
    return base_context


@app.get("/")
async def dashboard(
    request: Request,
    message: str | None = None,
    category: str | None = Query(default=None),
    media: str = Query(default="all"),
    sort: str = Query(default="newest"),
):
    stats = container.db.get_dashboard_stats()
    recent_bookmarks = container.db.list_bookmarks(
        limit=DEFAULT_RECENT_LIMIT,
        category=category or None,
        media=media,
        sort=sort,
    )
    return container.templates.TemplateResponse(
        name="dashboard.html",
        request=request,
        context=_template_context(
            request,
            stats=stats,
            recent_bookmarks=_serialize_bookmarks(recent_bookmarks),
            recent_category=category or "",
            recent_media=media,
            recent_sort=sort,
            message=message,
        ),
    )


@app.get("/search")
async def search(
    request: Request,
    q: str = Query(default=""),
    mode: str = Query(default="hybrid"),
    category: str | None = Query(default=None),
    collection_id: int | None = Query(default=None),
    media: str = Query(default="all"),
    sort: str = Query(default="relevance"),
    page: int = Query(default=1, ge=1),
):
    normalized_query = q.strip()
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    has_next_page = False
    total_count: int | None = None

    if normalized_query:
        fetch_limit = offset + DEFAULT_PAGE_SIZE + 1
        results = container.search_service.search(
            normalized_query,
            mode=mode,
            limit=fetch_limit,
            category=category or None,
            collection_id=collection_id,
            media=media,
            sort=sort,
        )
        has_next_page = len(results) > offset + DEFAULT_PAGE_SIZE
        paged_results = results[offset : offset + DEFAULT_PAGE_SIZE]
        cards = _serialize_search_results(paged_results)
    else:
        bookmarks = container.db.list_bookmarks(
            limit=DEFAULT_PAGE_SIZE,
            offset=offset,
            category=category or None,
            media=media,
            sort="newest" if sort == "relevance" else sort,
        )
        total_count = container.db.count_bookmarks(category=category or None, media=media)
        has_next_page = offset + DEFAULT_PAGE_SIZE < total_count
        cards = _serialize_bookmarks(bookmarks)

    showing_from = offset + 1 if cards else 0
    showing_to = offset + len(cards)
    context = _template_context(
        request,
        query=normalized_query,
        mode=mode,
        selected_category=category or "",
        selected_media=media,
        selected_sort=sort,
        current_page=page,
        per_page=DEFAULT_PAGE_SIZE,
        has_next_page=has_next_page,
        has_prev_page=page > 1,
        prev_page_url=_page_url(request, page - 1) if page > 1 else None,
        next_page_url=_page_url(request, page + 1) if has_next_page else None,
        total_count=total_count,
        showing_from=showing_from,
        showing_to=showing_to,
        cards=cards,
        page_title="All bookmarks",
    )
    if request.headers.get("HX-Request") == "true":
        return container.templates.TemplateResponse(
            name="partials/bookmark_list.html",
            request=request,
            context=context,
        )
    return container.templates.TemplateResponse(name="search.html", request=request, context=context)


@app.get("/bookmarks/{tweet_id}")
async def bookmark_detail(request: Request, tweet_id: str):
    tweet = container.db.get_tweet(tweet_id)
    if tweet is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    similar = container.search_service.find_similar(tweet_id)
    return container.templates.TemplateResponse(
        name="bookmark_detail.html",
        request=request,
        context=_template_context(request, tweet=tweet, similar=similar),
    )


@app.post("/sync")
async def manual_sync():
    try:
        result = await container.sync_service.sync_new_bookmarks()
        message = f"Sync finished. Added {result.added_count} new bookmarks."
    except Exception as exc:
        message = f"Sync failed: {exc}"
    return RedirectResponse(url=f"/?{urlencode({'message': message})}", status_code=303)


@app.post("/imports/manual")
async def manual_import(file: UploadFile = File(...)):
    try:
        payload = (await file.read()).decode("utf-8")
        result = container.import_service.import_payload(payload, filename=file.filename)
        message = (
            f"Import finished. Processed {result.imported_count} bookmarks, "
            f"added {result.new_count}, updated {result.updated_count}."
        )
    except Exception as exc:
        message = f"Manual import failed: {exc}"
    return RedirectResponse(url=f"/?{urlencode({'message': message})}", status_code=303)


@app.post("/collections")
async def create_collection(
    name: str = Form(...),
    description: str = Form(default=""),
):
    if not name.strip():
        return RedirectResponse(url="/?message=Collection+name+is+required", status_code=303)
    try:
        container.db.create_collection(name=name, description=description)
        message = "Collection created."
    except Exception as exc:
        message = f"Collection could not be created: {exc}"
    return RedirectResponse(url=f"/?{urlencode({'message': message})}", status_code=303)


@app.post("/collections/{collection_id}/items")
async def add_to_collection(collection_id: int, tweet_id: str = Form(...)):
    container.db.add_to_collection(collection_id=collection_id, tweet_id=tweet_id)
    return RedirectResponse(url=f"/bookmarks/{tweet_id}", status_code=303)


@app.get("/healthz")
async def healthcheck():
    return {"status": "ok"}
