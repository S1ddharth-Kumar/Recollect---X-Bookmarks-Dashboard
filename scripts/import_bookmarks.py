from __future__ import annotations

import sys
from pathlib import Path

from bookmarks_organizer.config import get_settings
from bookmarks_organizer.db import Database
from bookmarks_organizer.embeddings import build_embedding_provider
from bookmarks_organizer.manual_import import ManualImportService
from bookmarks_organizer.search import SearchService
from bookmarks_organizer.vector_store import SemanticIndex


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: uv run python scripts/import_bookmarks.py <path-to-json-or-csv>")

    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    settings = get_settings()
    db = Database(settings.database_path)
    db.initialize()
    provider = build_embedding_provider(settings.embedding_model, settings.embedding_dimension)
    search_service = SearchService(db, provider, SemanticIndex(db, prefer_faiss=settings.use_faiss))
    import_service = ManualImportService(db=db, search_service=search_service)
    summary = import_service.import_file(path)
    print(
        f"Processed {summary.imported_count} bookmarks; "
        f"added {summary.new_count}; updated {summary.updated_count}; "
        f"latest={summary.latest_bookmark_id}"
    )


if __name__ == "__main__":
    main()

