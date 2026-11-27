# TODO — core-lib
## High Priority (Bugs & Critical Fixes)

### 1. Dynamic Module Exports Missing `__all__`
- **Context:** `core_lib/discord/__init__.py` and `core_lib/gdrive/__init__.py` use `__getattr__` for lazy loading, but lack `__all__` or `.pyi` stubs.
- **Action Items:**
  - [x] Implement `__all__` or type stubs to improve static analysis and IDE symbol resolution.
  - [x] Add `tests/test_package_exports.py` to verify lazy-loading and attribute resolution.

### 2. GDrive Service Defensive Guardrails
- **Context:** 21 statements in `GDriveService` are unexercised (credential handling, API exceptions, folder access).
- **Action Items:**
  - [ ] Add tests for `_get_service()` returning `None`.
  - [ ] Refactor broad `Exception` handling to catch specific API errors.
  - [ ] Create tests for guard clauses in `file_exists`, `list_files`, `upload_file`, `download_file`, and `verify_folder_access`.

### 3. GDrive OAuth2 & Helper Edge Cases
- **Context:** Missing tests for `gdrive_auth.py` browser flow and `gdrive_helpers.py` error logging branches.
- **Action Items:**
  - [ ] Add test for `InstalledAppFlow` trigger when valid credentials exist but no token exists.
  - [ ] Add test for `verify_gdrive_folder_access` exception path (line 46).

## Medium Priority (Testing & Mutation Readiness)

### 4. Killing Surviving Mutants
- **Context:** Several mutants survive in the current test suite, masking logic errors.
- **Action Items:**
  - [ ] **Backoff Logic:** Assert exact `time.sleep` arguments in `scripts/gdrive_update_bot.py`.
  - [ ] **Metadata Injection:** Assert `call_args` on `files().create()` to verify `parents` list metadata in `GDriveService`.
  - [ ] **Discord Payloads:** Add tests for "embeds-only" messages (`content=None`) in `DiscordNotifier`.
  - [ ] **Timeout Handling:** Verify `timeout` kwargs in `DiscordNotifier` session posts.

### 5. Integration & Functional Gaps
- **Context:** Tests are "mock-saturated" and lack black-box verification.
- **Action Items:**
  - [ ] **HTTP/Retry Contract:** Implement contract tests or loopback fixtures to verify `HTTPAdapter` retry behavior.
  - [ ] **CLI Black-Box:** Create an out-of-process test for `scripts/gdrive_update_bot.py` verifying exit codes and STDOUT.
  - [ ] **Clean Import Verification:** Verify package importability in isolated environments (without optional extras).
---

## Future Enhancements
- [ ] Implement typed wrappers for Google API client resources.
- [ ] Migrate from `unittest.mock` to loopback integration fixtures where possible.

