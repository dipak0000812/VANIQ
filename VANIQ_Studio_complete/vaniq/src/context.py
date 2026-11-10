from __future__ import annotations

from dataclasses import dataclass

from src.config import Settings, load_settings
from src.storage.db import Database
from src.storage.repo import Repository


@dataclass
class AppContext:
    settings: Settings
    db: Database
    repo: Repository


def build_context(settings: Settings | None = None) -> AppContext:
    settings = settings or load_settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    return AppContext(settings=settings, db=db, repo=Repository(db))
