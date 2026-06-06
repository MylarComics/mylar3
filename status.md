# Project Status: mylar3

This file tracks the current features, environment status, and pending/completed tasks for mylar3 (comic book grabber fork).

## Environment Info
- **Language**: Python 3.14.3 (active virtual environment `.venv`)
- **Legacy Codebase Location**: [Mylar.py](file:///E:/Coding Projects/mylar3/.old/Mylar.py)
- **New Stack**: FastAPI + SQLModel (SQLAlchemy & Pydantic) + SQLite + HTMX / Alpine.js (Proposed)

## Current Status
- **Main codebase**: The legacy CherryPy application codebase has been successfully archived to [`.old/`](file:///E:/Coding Projects/mylar3/.old) for reference.
- **Recent changes**:
  - Moved legacy application folders (`mylar/`, `lib/`, `tests/`, etc.) and databases/configs to `.old/`.
  - Kept only virtual environment (`.venv`), rule standard configs, git files, and `status.md` in the root workspace.
  - Performed a comprehensive settings audit comparing the legacy codebase's settings definitions with the new FastAPI database/cache settings schema, capturing the mapping in a comparison report.

## Features Tracking
- [x] Archive legacy codebase to [`.old/`](file:///E:/Coding Projects/mylar3/.old)
- [x] Bootstrap FastAPI application backend
- [x] Integrate SQLModel for type-safe database access
- [x] Migrate/extract filename parsing and search logic from `.old/mylar`
  - [x] Extract and modernize filename parser (Phase 1)
  - [x] Port ComicVine API client, cover downloader, and db sync importer logic (Phase 2)
  - [x] Port search / RSS loops (Phase 3)
- [x] Build lightweight HTMX web GUI (Phase 4)
- [x] Implement async downloader client integrations (Phase 5)
  - [x] SABnzbd (HTTP JSON REST API)
  - [x] NZBGet (JSON-RPC)
  - [x] qBittorrent (WebAPI v2 with native bencode hash extraction)
  - [x] Transmission (JSON-RPC with CSRF session-token handling)
  - [x] `BaseDownloader` abstract interface + `get_downloader()` factory
  - [x] 26 passing unit tests across all four clients
- [x] Implement Celery Beat scheduled task runner (Phase 6)
  - [x] `app/core/sync_db.py` — psycopg2 sync engine for Celery workers
  - [x] `app/tasks/search_wanted.py` — periodic search loop for Wanted issues
  - [x] `app/tasks/grab_issue.py` — submit matches to downloader, update status to Snatched
  - [x] `app/tasks/db_sync.py` — on-demand ComicVine metadata refresh
  - [x] `app/worker.py` — expanded with beat_schedule, two queues (default + grabs)
  - [x] `docker-compose.yml` — added `celery_beat` service
  - [x] 11 passing unit tests (104 total, 0 failures)
- [x] Implement Apprise notification system (Phase 7)
  - [x] `app/notifications/base.py` — `BaseNotifier` ABC with async `notify()` interface
  - [x] `app/notifications/apprise_notifier.py` — Apprise backend (70+ services, URL-scheme config)
  - [x] `app/notifications/factory.py` — `get_notifier()` factory, lazy-loads when APPRISE_URLS is set
  - [x] `grab_issue.py` — snatch success + failure notification hooks
  - [x] `db_sync.py` — new-issue discovery notification hook
  - [x] `POST /api/notifications/test` — test endpoint for verifying Apprise setup
  - [x] 14 passing unit tests (118 total, 0 failures)
- [x] Implement Settings Management (Phase 8)
  - [x] `app/models/settings.py` — `SystemSettings` database table using SQLModel (fully expanded with all remaining legacy settings)
  - [x] `app/core/config.py` — extended settings with dynamic local filesystem cache reloading (`check_and_reload()`) and environment variable fallbacks
  - [x] `app/services/settings_service.py` — DB seeding, cache serialization (`cache/settings_cache.json`), and atomic update functions
  - [x] `app/templates/settings.html` — premium dark-themed configuration dashboard with tabbed HTMX sections, advanced downloader configs, new tabs (Torrents, Metatagging, Weekly pulls, Direct downloads), and interactive toasts
  - [x] Registered routes: `GET /settings` (web router) & `POST /api/settings` (API router)
  - [x] 4 passing unit tests (122 total, 0 failures)
  - [x] Completed manual settings verification audit using browser automation and verified saving capabilities


## Next Steps
- Run further user acceptance testing / manual flows in a staging environment.
- Add additional comic book provider scraper clients or custom file layout rules as requested.
