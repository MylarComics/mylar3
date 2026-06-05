# Project Status: mylar3

This file tracks the current features, environment status, and pending/completed tasks for mylar3 (comic book grabber fork).

## Environment Info
- **Language**: Python 3.14.3 (active virtual environment `.venv`)
- **Main Entrypoint**: [Mylar.py](file:///E:/Coding Projects/mylar3/Mylar.py)
- **Dependencies**: Specified in [requirements.txt](file:///E:/Coding Projects/mylar3/requirements.txt)
- **Test Runner**: pytest (`.\.venv\Scripts\python -m pytest tests`)

## Current Status
- **Main codebase**: Functional but runs on legacy patterns (CherryPy web server, custom scheduler, custom DB mappings).
- **Recent changes**:
  - Added new logger module [mylar_logger_new.py](file:///E:/Coding Projects/mylar3/mylar_logger_new.py) (saved in UTF-16LE encoding).
- **Test Status**:
  - Out of 235 tests: 234 pass, 1 fails (`tests\test_queues.py::test_ddl_cleanup_keep_cache` due to a mockito mock expectation mismatch with Python 3.14 frozen `os` module).

## Features Tracking
- [x] CherryPy Web Server (Core GUI)
- [x] Database migration & maintenance scripts
- [x] Active logs & new logger module
- [x] Test suite stability (fixed mockito `os` mock under Python 3.14)
- [ ] Custom comic grabber features (to be designed/implemented)

## Next Steps
1. Initialize local project rules and status configuration.
2. Fix the failing test in `tests/test_queues.py`.
3. Plan custom comic grabber features requested by the user.
