from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bookmarks_organizer.config import Settings, get_settings
from bookmarks_organizer.db import Database
from bookmarks_organizer.embeddings import build_embedding_provider
from bookmarks_organizer.manual_import import ManualImportService
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
async def dashboard(request: Request, message: str | None = None):
    stats = container.db.get_dashboard_stats()
    recent_bookmarks = container.db.list_recent_bookmarks(limit=12)
    return container.templates.TemplateResponse(
        name="dashboard.html",
        request=request,
        context=_template_context(
            request,
            stats=stats,
            recent_bookmarks=recent_bookmarks,
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
):
    results = container.search_service.search(
        q,
        mode=mode,
        category=category or None,
        collection_id=collection_id,
    )
    context = _template_context(
        request,
        query=q,
        mode=mode,
        selected_category=category or "",
        selected_collection_id=collection_id,
        results=results,
        page_title="Search bookmarks",
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
