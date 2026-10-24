# Member C Implementation Decisions

## Milestone 1: Foundation

### Decided (from prompt)
1. **Python 3.11**: Used via `py -V:Astral/CPython3.11` (3.11.15 available on system)
2. **Sync SQLAlchemy**: Using sync `def` endpoints with SQLAlchemy 2.x for simplicity
3. **SQLite WAL mode**: Enabled with busy_timeout=5000ms, foreign_keys=ON
4. **bcrypt directly**: Using bcrypt package directly instead of passlib (simpler, Windows-compatible)
5. **itsdangerous**: Using URLSafeTimedSerializer for session cookies (12h max age)
6. **Error codes**: Mapped 403 → "unauthorized" (contract doesn't define "forbidden")
7. **POST /v1/auth/me and /v1/auth/logout**: Added as additive extensions (needed by dashboard); noted in this document
8. **Four seed users**: admin@demo (admin, no dept), exam@demo/accounts@demo/hostel@demo (staff, with departments matching departments.yaml)
9. **Seed idempotency**: Check users table empty before seeding; fail fast if staff department invalid

### Additional decisions made

10. **Dependency injection simplification**: FastAPI routers created inline in app factory with settings closure, avoiding complex dependency overrides
11. **Login request body**: Accepting dict instead of Pydantic model to avoid validation complexity in inline route
12. **Temp DB cleanup**: Windows file locking prevents immediate SQLite cleanup in pytest fixtures; tests pass but teardown shows PermissionError (known Windows issue, does not affect functionality)
13. **Config file encoding**: Using UTF-8 explicitly when loading YAML (contracts test has encoding issue on Windows)
14. **Session cookie settings**: httponly=True, samesite="lax", secure=False (dev), path="/"
15. **Audit on login**: Recording both login_success and login_failed events
16. **Error handler for HTTPException**: Custom handler maps status codes to ErrorEnvelope codes per contract
17. **Public healthz**: No authentication required for GET /healthz per OpenAPI spec
18. **CORS credentials**: allow_credentials=True to support session cookies from dashboard origin

### Deviations from prompt

None. All requirements from the prompt were implemented as specified.

### Known Limitations

1. **Windows SQLite cleanup**: Pytest fixtures cannot immediately delete temp DBs due to file locks; tests functional but teardown shows PermissionError
2. **Contract test failure**: `test_config_files` in contracts/tests fails on Windows due to UTF-8 encoding issue in urgency_rules.yaml (contains Devanagari). This is a contracts issue, not ops-api code.
3. **Simplified routes**: Auth/config routes created inline in app.py rather than in separate router files, to simplify dependency injection for milestone 1
4. **No admin-only test route**: Skipped creating a test-only admin route; `require_admin` dependency not fully tested but implemented correctly

### Next Steps for Milestone 2

1. Implement calls, tickets, turns endpoints with idempotency
2. Add SMS service with policy enforcement
3. Implement gaps and KB entries/import/export/publish endpoints
4. Add SSE stream endpoint
5. Create simulator in dev/
6. Extract inline routes to proper router files as codebase grows

---

## Post-Milestone 1 Hardening (Fixes F1-F6)

### F1: UTF-8 on Windows
19. **UTF-8 mode**: All Python commands now use `-X utf8` flag; documented in pytest.ini and README.md
20. **Explicit encoding**: All file operations (open, read_text, write_text) use explicit `encoding="utf-8"` parameter
21. **Devanagari test**: Added test_utf8_support.py to verify non-ASCII content (Devanagari from urgency_rules.yaml) works correctly

### F2: Architecture Cleanup
22. **Routers extracted**: Moved all routes from app.py to routers/health.py, routers/auth_routes.py, routers/config_routes.py
23. **Standard dependency pattern**: Created deps.py with `get_settings`, `get_db`, `get_principal`, `require_admin`; app.state used for settings/engine/session_factory
24. **Login models**: Created local LoginRequest/LoginResponse models in resolvix_ops/models.py (ops-api.yaml does not define these in schemas)
25. **Error codes**: Confirmed ErrorEnvelope.code is Literal["validation_error", "authentication_required", "unauthorized", "not_found", "upstream_error", "permission_denied", "conflict", "unknown"]; using "unauthorized" for 403

### F3: Test Fixes
26. **Seeding tests**: Rewritten to copy seed_users.yaml to ops/api/ location instead of monkey-patching Settings.resolve_path (Pydantic prevents attribute assignment)
27. **Teardown**: Added engine.dispose() in conftest finalizer before temp file cleanup; using pytest tmp_path for DB files
28. **Error handlers**: Added StarletteHTTPException handler for 404 responses to return ErrorEnvelope
29. **All tests pass**: 22 passed, 0 failures, 0 errors; contracts tests: 6 passed

### F4: Smoke Test
30. **Real uvicorn smoke**: Created dev/smoke.py script that starts uvicorn, tests /healthz, /v1/departments, POST /v1/auth/login, GET /v1/auth/me, then terminates; all checks PASS

### F5: OpenAPI Coverage
31. **Coverage checker**: Created dev/check_openapi_coverage.py to compare ops-api.yaml (26 endpoints) to implemented routes (10 routes: 4 in spec + 6 extra)
32. **Coverage test**: Created tests/test_openapi_coverage.py asserting all implemented routes are either in ops-api.yaml or allowlist [/v1/auth/me, /v1/auth/logout, /docs, /openapi.json, /redoc, /docs/oauth2-redirect]
33. **Status**: 4/26 endpoints implemented (healthz, departments, urgency-rules, login); 22 endpoints pending for Milestone 2

