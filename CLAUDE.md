# mylar3 - Project Rules & Skills

This file defines the structure for local workspace rules and skills.

## 🚀 Post-Change Verification Protocol
You **MUST** run the project verification command after every code change to guarantee stability and prevent regressions.

### Rebuild and Verify Command
Run the following command from the workspace root:
```bash
.\.venv\Scripts\python -m pytest tests
```

> [!IMPORTANT]
> 1. Never skip verification before committing. The verification step **MUST** execute all unit and integration test suites.
> 2. You **MUST** update the [status.md](file:///./status.md) file after each task to reflect the current status of features, completed tasks, and architectural changes.
> 3. You **MUST** generate a git commit with an accurate, descriptive commit message representing the changes after every successful execution (only if a Git repository is initialized in the workspace; skip this step if Git is not initialized).

## 🧪 Automated Testing & Bug Prevention
To ensure that projects are robust enough to share with others, you must establish and maintain strict testing habits:

1. **Test Coverage**: Write automated unit and/or integration tests for all new features, API endpoints, and core business logic.
2. **Bug Fix Verification**: When fixing a bug, write a test case that reproduces the bug, verify that it fails, and then verify that it passes after the fix is implemented.
3. **Robust Input Validation**: Ensure tests check boundary conditions, invalid inputs, error handling paths, and API constraints to catch bugs before they reach runtime.
4. **Zero-Failure Tolerance**: All automated tests must pass successfully before a task is considered complete.
5. **Dynamic View & API Route Sanity Checking**: Implement and maintain a dynamic route scanner test that loops through all registered HTML and API endpoints to verify that GET requests do not trigger compile or `500 Internal Server Errors`. For API paths, ensure they return valid JSON structures and appropriate status codes, providing instant compile coverage for the entire routing tree.
6. **Fail-on-Unexpected-Errors**: Configure the test runner or assertions to capture log outputs. Any unexpected `ERROR` or `CRITICAL` logs written during a test execution must fail the test run, transforming silent, swallowed exceptions into loud, test-failing assertions.
7. **Shared Mock Fixtures**: Centralize mock payloads and external API responses (e.g. TMDB, Plex) into a shared test fixtures folder. Test suites must reuse these mock utilities and decorators instead of writing repetitive inline mocks, saving token quota and maintaining mock consistency.

## 💎 Code Quality & Production Standards
All generated code must be clean, maintainable, and production-ready.

1. **Imports**:
   - Write all imports at the top of the file.
   - **No lazy imports** inside functions or methods unless absolutely required for dynamic loading or avoiding circular dependencies (documented with clear comments).
   - Order imports logically (standard library, third-party libraries, local imports).

2. **Types & Schemas**:
   - Add type hints to all Python function signatures, variables, and return values (or use language-appropriate typing standards).
   - Use standard data schemas (e.g. Pydantic models in Python, TypeScript interfaces in TS) for API payloads and database records.

3. **Error Handling & Logging**:
   - Do not use broad `except Exception:` blocks without logging or re-raising.
   - Use built-in logging libraries instead of raw print/console statements in production code.
   - **Mylar Logging Standard**: Keep Mylar's existing straightforward logging pattern. Use `logger.info`, `logger.warn`, `logger.error`, and `logger.debug`/`logger.fdebug` for tracing. Honor the `loglevel` config setting and the verbose debugging toggle (`logger.fdebug` / `logger.debug` should only write when `mylar.LOG_LEVEL >= 2`). Ensure logs remain clean, plain-text, and easily readable without unnecessary clutter.

4. **Aesthetics & UI Standards**:
   - Maintain a premium visual design: consistent typography, harmonious color palettes, smooth transitions, proper margins, and descriptive spacing.
   - Do not use inline styles or raw CSS files unless explicitly requested. Always utilize the established local utility framework (like Tailwind CSS) and existing UI primitives.
   - Ensure the GUI is fully responsive and optimized for mobile viewports (supporting touch-friendly targets, collapsible navigation, adaptive grid counts, and screen-fitting wrappers). Do not focus exclusively on desktop layouts; verify responsiveness on multiple screen sizes.

5. **Framework & Architecture Decisions**:
   - When introducing new frameworks, major dependencies, or architectural shifts, present 2-3 viable options detailing the pros, cons, and trade-offs of each, and wait for user approval before executing.

6. **Modular Architecture & Code Separation**:
   - Avoid monolithic files. Keep files modular by separating logic into distinct files and sub-modules.
   - Limit file sizes (ideally under 500 lines) and function/method complexity.
   - Extend base objects or classes by importing them locally and building extensions in separate files rather than piling all behavior into a single base definition file.

7. **Security & Secrets Safety**:
   - Never hardcode private keys, database credentials, API tokens, or secrets. Always pull them from environment configurations or system environments.

8. **Environment Configurations**:
   - When introducing new variables to `.env`, immediately document them in `.env.example` with placeholders or dummy values to prevent configuration drift.

9. **No Code Stubs**:
    - Never write code stubs, temporary `TODO` comments, or truncated snippets (e.g., `// ... rest of code remains the same`). Code edits must always be fully complete and ready to run.

10. **Conventional Commits**:
    - Write git commit messages using the Conventional Commits specification (e.g., `feat:`, `fix:`, `test:`, `refactor:`, `chore:`, `docs:`) with descriptive subject lines under 50 characters.

11. **Consistent Deployment of Fixes**:
    - Ensure that all fixes, database initialization tasks, custom commands, or setup migrations are programmatically encoded into startup or configuration files (such as `entrypoint.sh`, `docker-compose.yml`, or migration modules). Never rely on manual runtime CLI execution to maintain the application. This ensures a consistent and reproducible experience across development, staging, and production instances.

12. **Living Rules Document (AGENTS.md)**:
    - Proactively update the project's `AGENTS.md` rules file whenever repository-specific findings, quirks, or hidden behaviors are discovered during tasks. Treating `AGENTS.md` as a living documentation file ensures subsequent agent sessions build upon shared repository context without losing history.

13. **Upfront Plan Alignment & Ambiguity Resolution**:
    - For any non-trivial tasks (e.g., changes affecting database schemas, API routes, or multi-component UI states), draft an `implementation_plan.md` first. Recommend the `/grill-me` command to the user to run an interactive interview to align on design decisions, color choices, and logical constraints before writing code. This saves time, limits refactoring, and conserves token quota.

14. **Proactive Connection & Service Integration Diagnostics**:
    - Always verify that the database and third-party services are fully reachable and authenticated before and after introducing integration changes. Run a verification check, diagnostic script, or pre-flight check to isolate API/connection issues from logical bugs.

15. **Zero-Downtime Migration Safety**:
    - Ensure database migrations handle existing data without data loss or downtime. Verify that new columns have default values or allow nulls, and ensure the application remains compatible during deployment transition states.

16. **Multi-LLM Rules Synchronization (Multi-Format Rules)**:
    - To ensure that project rules, verification commands, and quality standards are respected by different LLM assistants (such as Gemini, Claude, Cursor, and Windsurf), always mirror and synchronize these project rules across the formats expected by each platform:
      - `AGENTS.md` (for Gemini/Antigravity)
      - `CLAUDE.md` (for Claude Code / Claude CLI)
      - `.cursorrules` (for Cursor AI)
      - `.windsurfrules` (for Windsurf)
    - Whenever you update the project's rules or discover repository-specific behavior, make sure to propagate those changes to all of these formats to maintain alignment.

17. **Automatic Workspace Rules Synchronization**:
    - At the start of every session, check if the local rules files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.windsurfrules`) exist and match the latest global template `C:\Users\caste\.gemini\project.md`. If they are out of sync, outdated, or missing, immediately perform a synchronization cycle to update them, ensuring that the latest global standards are consistently applied across all projects without manual user intervention.

18. **Zero-Config Onboarding & .env Bootstrapping**:
    - If a local `.env` configuration file is missing on startup or initialization, the agent must automatically copy `.env.example` to `.env`, generate secure random secret keys for session/cryptographic signatures (replacing placeholders), and configure default local ports/credentials so the stack can run out-of-the-box.

19. **Dependency Reconciliation**:
    - Whenever package metadata files (e.g. `requirements.txt`, `package.json`, `Gemfile`, `Cargo.toml`) are modified, the agent must immediately execute the corresponding package installer or container rebuild command to keep the active runtime environment synchronized.

20. **Workspace Health Diagnostics (Doctor)**:
    - Maintain a workspace diagnostic script (`doctor.py` or similar) that validates database migrations, checks local network loops, tests external integration endpoints, and verifies service reachability. Run this script first when troubleshooting stack issues to isolate configuration/network drift from code bugs.

21. **Secrets Safety in Diffs**:
    - Never write raw secrets, private keys, database passwords, or active API credentials into any code file, even temporarily for local testing. All credentials must be loaded dynamically from environment variables, and testing environments must rely exclusively on mocked values or dummy tokens to prevent accidental git commits of sensitive data.

22. **Maintain Git Exclusion Policies (.gitignore)**:
    - Actively maintain the `.gitignore` file to ensure that local database files (e.g. `db.sqlite3` or local data directories), local logs, runtime caches, and sensitive environment config files (like `.env`) are strictly excluded from the repository. Review `.gitignore` whenever introducing new persistent files, logs directories, or local configuration files to prevent untracked local state from being committed.

23. **Single Page App (SPA) UX Behavior & Dynamic Rendering**:
    - Ensure all user interface applications are designed to dynamically render changes, page content, and state transitions without forcing a full page refresh.
    - Maintain standard multi-page and deep-linking capabilities by combining technologies like HTMX, Alpine.js, or custom JavaScript pushState/history API controls. Navigation and dynamic layout shifts must preserve clean browser histories and distinct shareable URLs, delivering a fluid, single-page app feel while retaining searchability and page structures.

## 💡 Token & Quota Conservation Rules
To maintain high speed and prevent burning through API limits:

1. **Diff-Only Modifications**:
   - Never overwrite a whole code file to make small edits. Always use targeted replacements (`replace_file_content` or `multi_replace_file_content` on specific line ranges) to minimize token transfer.
