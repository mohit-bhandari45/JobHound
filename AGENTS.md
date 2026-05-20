# JobHound — Agent Context

> **Purpose:** This file helps AI agents understand and work effectively with the JobHound codebase.

## Project Identity

**JobHound** is a fullstack web application currently in early development. It is structured as a monorepo with a Python (FastAPI) backend, a React (TypeScript + Vite) frontend, and a PostgreSQL database.

The project serves as a job tracking / application management tool (exact feature set is TBD; the codebase is a starter/template right now).

## Directory Structure

```
.
├── AGENTS.md                 # ← You are here
├── README.md                 # Human-facing overview (minimal)
├── LICENSE
├── docker-compose.yml        # Dev orchestration (db, server, web)
├── Dockerfile                # Production single-image build
├── nginx.conf                # Production reverse proxy config
├── supervisord.conf          # Production process manager config
├── .moon/
│   └── workspace.yml         # Moon monorepo workspace config
├── .gitignore
├── apps/
│   ├── server/               # FastAPI backend
│   │   ├── main.py           # Application entrypoint
│   │   ├── pyproject.toml    # Python dependencies (uv)
│   │   ├── uv.lock           # Locked Python dependencies
│   │   ├── .python-version   # 3.13
│   │   ├── moon.yml          # Moon tasks for server
│   │   └── Dockerfile.dev    # Dev container image
│   └── web/                  # React + Vite frontend
│       ├── src/
│       │   ├── App.tsx       # Root component
│       │   ├── main.tsx      # Entrypoint
│       │   ├── index.css     # Global styles (light/dark)
│       │   └── App.css       # Component styles
│       ├── package.json      # JS dependencies (bun)
│       ├── bun.lock          # Locked JS dependencies
│       ├── vite.config.ts    # Vite + proxy config
│       ├── tsconfig.json     # TypeScript project references
│       ├── moon.yml          # Moon tasks for web
│       └── Dockerfile.dev    # Dev container image
```

## Tech Stack

| Layer         | Technology           | Package Manager |
|---------------|----------------------|-----------------|
| Monorepo      | [moon](https://moonrepo.dev) | —               |
| Backend       | Python 3.13, FastAPI | [uv](https://github.com/astral-sh/uv) |
| Frontend      | React 19, TypeScript, Vite | [bun](https://bun.sh) |
| Database      | PostgreSQL 15        | —               |
| Reverse Proxy | Nginx                | —               |
| Process Mgr   | Supervisor           | —               |
| Container     | Docker               | —               |

## Development Workflow

### Option A: Moon (recommended for host dev)

From the repo root:

```bash
# Install all project dependencies
moon run server:install web:install

# Start both frontend and backend (in separate terminals, or background)
moon run server:dev   # uv run fastapi dev --host 0.0.0.0 --port 8000
moon run web:dev      # bun run dev
```

### Option B: Docker Compose (full stack)

```bash
docker compose up --build
```

This starts:
- `db` on port `5432` (PostgreSQL)
- `server` on port `8000` (FastAPI dev server)
- `web` on port `5173` (Vite dev server with HMR)

The `web` container proxies `/api` to the `server` container automatically.

### Option C: Manual per-app

**Backend (`apps/server`)**
```bash
cd apps/server
uv sync              # install deps
uv run fastapi dev --host 0.0.0.0 --port 8000
```

**Frontend (`apps/web`)**
```bash
cd apps/web
bun install          # install deps
bun run dev          # starts Vite dev server
```

## API Conventions

- All backend endpoints are exposed through the **FastAPI app** (`apps/server/main.py`).
- The frontend accesses them via `/api/*` (e.g., `fetch('/api')`).
- **Dev:** Vite's dev server proxies `/api` to `http://localhost:8000` (or `http://server:8000` inside Docker).
- **Production:** Nginx proxies `/api` to the internal Uvicorn server on `127.0.0.1:8000`.

The trailing slash in `proxy_pass` strips the `/api` prefix before forwarding.

## Deployment Architecture

The production `Dockerfile` produces a **single container** that runs everything:

1. **PostgreSQL** — local database inside the container.
2. **Uvicorn** — runs the FastAPI backend (`uv run uvicorn main:app ...`).
3. **Nginx** — serves the static React build and proxies `/api` to Uvicorn.

All three processes are managed by **Supervisor** (`supervisord.conf`). The image exposes port `80`.

```
┌──────────────────────────────┐
│          Container (80)       │
│  ┌─────────────────────────┐ │
│  │  Nginx                  │ │
│  │  ├── / → static HTML    │ │
│  │  └── /api → Uvicorn     │ │
│  └─────────────────────────┘ │
│  ┌─────────────────────────┐ │
│  │  Uvicorn (8000)         │ │
│  │  FastAPI (main.py)      │ │
│  └─────────────────────────┘ │
│  ┌─────────────────────────┐ │
│  │  PostgreSQL             │ │
│  └─────────────────────────┘ │
│  Managed by Supervisor        │
└──────────────────────────────┘
```

## Environment Variables

| Variable       | Default (dev)                | Description                        |
|----------------|------------------------------|------------------------------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@db:5432/postgres` | PostgreSQL connection string |
| `API_URL`      | `http://localhost:8000`      | Backend URL for Vite proxy         |

## Build & Dependency Management

- **Python:** `pyproject.toml` + `uv.lock` — use `uv sync` to install, `uv sync --frozen` in Docker.
- **JavaScript:** `package.json` + `bun.lock` — use `bun install` to install, `bun install --frozen-lockfile` in Docker.

Lockfiles are committed. Do not delete or ignore them.

## Key Configuration Files Reference

| File | Role |
|------|------|
| `.moon/workspace.yml` | Declares `apps/*` and root as moon projects. |
| `apps/server/moon.yml` | Defines `install`, `dev`, `start` tasks for backend. |
| `apps/web/moon.yml` | Defines `install`, `dev`, `start` tasks for frontend. |
| `docker-compose.yml` | Spins up `db`, `server`, and `web` in dev. |
| `Dockerfile` | Multi-stage production build (frontend → Python + Postgres + Nginx). |
| `nginx.conf` | Production reverse proxy; SPA fallback; `/api` passthrough. |
| `supervisord.conf` | Production process definitions (postgres, uvicorn, nginx). |
| `apps/web/vite.config.ts` | Vite + React plugin; `/api` proxy config. |

## Notes for Agents

- The frontend is a standard **Vite + React** SPA. The build output goes to `dist/`.
- The backend is a minimal FastAPI app. Expand `main.py` or split into routers as needed.
- **Do not run `git commit`, `git push`, or other git mutations unless explicitly asked.**
- When adding new features, prefer minimal changes and follow the existing patterns (e.g., `uv` for Python, `bun` for JS, `moon` for orchestration).
