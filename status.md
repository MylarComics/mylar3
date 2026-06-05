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
  - Integrated `log_memory` function into [logger.py](file:///E:/Coding Projects/mylar3/mylar/logger.py) for tracking system memory footprint.
  - Deleted temporary UTF-16LE `mylar_logger_new.py`.
- **Test Status**:
  - Out of 235 tests: 235 pass, 0 fails (mockito verification fix applied for python 3.14).

## Features Tracking
- [x] CherryPy Web Server (Core GUI)
- [x] Database migration & maintenance scripts
- [x] Active logs & integrated memory logger
- [x] Test suite stability (fixed mockito `os` mock under Python 3.14)
- [ ] Custom comic grabber features (to be designed/implemented)

## Next Steps
1. Gather requirements for the custom comic grabber functionality.
2. Outline implementation plan for the custom features.

