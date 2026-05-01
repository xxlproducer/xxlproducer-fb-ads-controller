# FB Ads Controller

A local, single-user web app for managing your Facebook ad accounts —
inspired by tools like OptiBOX, but trimmed down to the essentials and
built to run entirely on your own PC. Nothing leaves your machine.

> Status: **MVP scaffold (Week 1).** Token management is functional;
> Dashboard / Bulk actions / Autozaliv are placeholders that ship in the
> next iterations.

## What's inside

| Layer    | Stack                                                 |
| -------- | ----------------------------------------------------- |
| Backend  | Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite, httpx  |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, lucide-react |
| Auth     | Server-side session cookies (single-user)             |
| Storage  | One SQLite file in `backend/data/`                    |

## Features (current iteration)

- **First-run setup** — creates a local admin account on first launch
- **Login / logout** with session cookies
- **Connect FB tokens** with live validation against the Graph API
  (`/me`, `/me/permissions`)
- **Per-token proxy** support for routing Graph API calls through
  HTTP/HTTPS/SOCKS proxies
- **Aggregated ad-account view** across all connected tokens
  (currency, timezone, balance, spent)
- **Re-sync** any token on demand (refresh status + scopes + accounts)
- **Apple-style UI** — clean light/dark theme, generous spacing,
  glass-blur surfaces

## What's coming next

- **Dashboard** with metrics across all accounts (impressions, clicks,
  spend, results, purchases) using ag-Grid
- **Bulk actions** — pause / activate / delete campaigns, adsets, ads
  across many accounts at once
- **Autozaliv** — multi-step wizard to launch Sales / Purchase
  campaigns with creative upload and multi-account multiplication

## Quick start (Windows)

Requirements: **Python 3.10+** and **Node.js 18+** on `PATH`.

1. Clone or download this repo.
2. Double-click **`setup.bat`** once. It will:
   - create a Python virtual environment in `backend/.venv`
   - install backend dependencies
   - install frontend dependencies
3. Double-click **`run.bat`** to start the app. Two console windows
   will open (backend + frontend) and your browser will navigate to
   `http://localhost:5173`.
4. On first launch you'll see the **first-time setup** screen — pick a
   username and password. These are stored locally in
   `backend/data/fb_ads_controller.db`.
5. Sign in, go to **FB Accounts**, and click **Connect token**. Paste a
   long-lived FB user access token with the scopes:
   `ads_management`, `ads_read`, `business_management`, `read_insights`.

To stop the app, close both console windows.

## Quick start (macOS / Linux)

```bash
./run.sh
```

The script handles dependency setup automatically on first run.

## Project layout

```
fb-ads-controller/
├─ backend/
│  ├─ app/
│  │  ├─ api/          # FastAPI routers: auth, tokens, fb_accounts, health
│  │  ├─ core/         # config, security helpers
│  │  ├─ db/           # SQLAlchemy engine + session
│  │  ├─ models/       # ORM models: User, FbToken
│  │  ├─ schemas/      # Pydantic request/response models
│  │  ├─ services/     # FbClient (Graph API wrapper)
│  │  └─ main.py       # FastAPI app + middleware + router wiring
│  ├─ data/            # SQLite DB (gitignored)
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ components/   # Layout, Sidebar, ui/{Button,Input,Card}
│  │  ├─ lib/          # api client, auth context, utils
│  │  └─ pages/        # Login, Tokens, Placeholder
│  ├─ index.html
│  ├─ tailwind.config.js
│  └─ vite.config.ts
├─ run.bat / run.sh    # one-click launcher
└─ setup.bat           # first-time install
```

## Configuration

The backend reads optional environment variables (or a `.env` file in
`backend/`):

| Variable     | Default                                | Meaning                  |
| ------------ | -------------------------------------- | ------------------------ |
| `SECRET_KEY` | random per first-run                   | Cookie signing secret    |
| `HOST`       | `127.0.0.1`                            | Backend bind address     |
| `PORT`       | `8080`                                 | Backend port             |
| `DATA_DIR`   | `data`                                 | Where SQLite + uploads live |
| `FB_API_VERSION` | `v21.0`                            | Graph API version        |
| `CORS_ORIGINS` | `http://localhost:5173`              | Comma-separated origins  |

## Security notes

- The DB stores raw access tokens. This is acceptable for a **personal,
  local, single-user** tool — the file lives only on your PC. Do not
  expose this app to the public internet without adding encryption at
  rest and proper authentication.
- The API never returns the raw `access_token` in list responses.
- Pre-commit hooks and CI are intentionally not configured yet.

## License

Private — internal use only.
