# Resolvix Ops API (Member C)

Backend for ops dashboard, tickets, SMS, and knowledge base management.

## Setup

```powershell
# Create venv with Python 3.11
py -V:Astral/CPython3.11 -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1

# Install contracts
pip install -e ../../contracts/python

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Install package in editable mode
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:
- `SERVICE_KEY`: Shared key for runtime authentication
- `SESSION_SECRET`: 32+ character secret for session cookies
- `SEED_PASSWORD`: Default password for seed users
- Other settings per `.env.example`

## Run Tests

**Important:** Always run Python with UTF-8 mode on Windows to handle non-ASCII content in config files:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests -v
```

Or from project root:

```powershell
cd ops/api
python -X utf8 -m pytest
```

## Run Server

```powershell
.\.venv\Scripts\python.exe -X utf8 -m uvicorn resolvix_ops.app:app --port 8100 --loop asyncio --workers 1
```

For auto-reload during development:

```powershell
python -X utf8 -m uvicorn resolvix_ops.app:app --port 8100 --reload
```

## Smoke Test

```powershell
python -X utf8 dev/smoke.py
```

## Project Structure

```
ops/api/
├── resolvix_ops/         # Main package
│   ├── routers/          # Route handlers
│   ├── app.py            # Application factory
│   ├── config.py         # Settings
│   ├── db.py             # Database session
│   ├── orm.py            # SQLAlchemy models
│   ├── auth.py           # Authentication
│   ├── audit.py          # Audit logging
│   └── errors.py         # Error handlers
├── tests/                # Pytest tests
├── dev/                  # Development utilities
├── data/                 # SQLite database (gitignored)
└── .venv/                # Virtual environment (gitignored)
```

## API Documentation

Once running, visit:
- http://localhost:8100/docs (Swagger UI)
- http://localhost:8100/redoc (ReDoc)
