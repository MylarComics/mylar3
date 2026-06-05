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
- [ ] Bootstrap FastAPI application backend
- [ ] Integrate SQLModel for type-safe database access
- [ ] Migrate/extract filename parsing and search logic from `.old/mylar`
- [ ] Build lightweight HTMX web GUI

## Next Steps
1. Draft the implementation plan to bootstrap the new FastAPI backend.
2. Outline the first set of extracted functions (e.g., matching algorithms from `.old/mylar/filechecker.py`).


