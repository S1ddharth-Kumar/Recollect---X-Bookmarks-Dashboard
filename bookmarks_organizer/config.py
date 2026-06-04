from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = "Twitter/X Bookmarks Organizer"
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    data_dir: Path = field(init=False)
    database_path: Path = field(init=False)
    vector_index_path: Path = field(init=False)
    browser_profile_dir: Path = field(init=False)
    templates_dir: Path = field(init=False)
    static_dir: Path = field(init=False)
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    embedding_dimension: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIMENSION", "384")))
    sync_headless: bool = field(default_factory=lambda: _bool_env("SYNC_HEADLESS", False))
    scheduler_enabled: bool = field(default_factory=lambda: _bool_env("SCHEDULER_ENABLED", True))
    scheduler_day_of_week: str = field(default_factory=lambda: os.getenv("SCHEDULER_DAY_OF_WEEK", "sun"))
    scheduler_hour: int = field(default_factory=lambda: int(os.getenv("SCHEDULER_HOUR", "9")))
    scheduler_minute: int = field(default_factory=lambda: int(os.getenv("SCHEDULER_MINUTE", "0")))
    use_faiss: bool = field(default_factory=lambda: _bool_env("USE_FAISS", True))
    max_sync_scrolls: int = field(default_factory=lambda: int(os.getenv("MAX_SYNC_SCROLLS", "40")))
    max_sync_batch: int = field(default_factory=lambda: int(os.getenv("MAX_SYNC_BATCH", "250")))
    login_wait_seconds: int = field(default_factory=lambda: int(os.getenv("LOGIN_WAIT_SECONDS", "90")))

    def __post_init__(self) -> None:
        self.data_dir = Path(os.getenv("DATA_DIR", self.project_root / "data"))
        self.database_path = Path(os.getenv("DATABASE_PATH", self.data_dir / "bookmarks.db"))
        self.vector_index_path = Path(os.getenv("VECTOR_INDEX_PATH", self.data_dir / "vectors.faiss"))
        self.browser_profile_dir = Path(
            os.getenv("BROWSER_PROFILE_DIR", self.data_dir / "browser-profile")
        )
        self.templates_dir = self.project_root / "templates"
        self.static_dir = self.project_root / "static"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.browser_profile_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

