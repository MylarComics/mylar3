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

## Features Tracking
- [x] Archive legacy codebase to [`.old/`](file:///E:/Coding Projects/mylar3/.old)
- [x] Bootstrap FastAPI application backend
- [x] Integrate SQLModel for type-safe database access
- [x] Migrate/extract filename parsing and search logic from `.old/mylar`
  - [x] Extract and modernize filename parser (Phase 1)
  - [x] Port ComicVine API client, cover downloader, and db sync importer logic (Phase 2)
  - [x] Port search / RSS loops (Phase 3)
- [ ] Build lightweight HTMX web GUI

## Next Steps
1. Build lightweight HTMX web GUI (Phase 4).


