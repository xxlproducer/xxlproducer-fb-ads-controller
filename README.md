# FB Ads Controller

A local, single-user web app for managing your Facebook ad accounts —
inspired by tools like OptiBOX, but trimmed down to the essentials and
built to run entirely on your own PC. Nothing leaves your machine.

> Status: **Weeks 1-4 complete.** Token management, Dashboard with
> metrics, Bulk actions (pause/activate/delete), and Autozaliv
> (template-based campaign + adset launch across many accounts) all
> functional.

## What's inside

| Layer    | Stack                                                 |
| -------- | ----------------------------------------------------- |
| Backend  | Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite, httpx  |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, lucide-react |
| Auth     | Server-side session cookies (single-user)             |
| Storage  | One SQLite file in `backend/data/`                    |

## Features

- **First-run setup** — creates a local admin account on first launch
- **Login / logout** with session cookies
- **Connect FB tokens** with live validation against the Graph API
- **Per-token proxy** support (HTTP/HTTPS/SOCKS)
- **Aggregated ad-account view** across all connected tokens
- **Dashboard** with metrics across all accounts (impressions, clicks,
  spend, purchases, ROAS) — date presets, group-by levels
- **Bulk actions** — pause / activate / delete campaigns, adsets, ads
  across many accounts at once with concurrency-safe rate limiting
- **Autozaliv wizard** — template-based Campaign + AdSet launch
  across many accounts (with mandatory DSA fields for EU targeting)

## What's coming next

- **Week 5: Ad creatives** — image/video upload + Ad creation
  attached to existing AdSets across many accounts

## Quick start (Windows) — one-click launcher

Requirements: **Python 3.10+** and **Node.js 18+** on `PATH`.

1. Download the ZIP from the green **Code → Download ZIP** button on
   GitHub, or [click here](https://github.com/xxlproducer/xxlproducer-fb-ads-controller/archive/refs/heads/main.zip).
2. Extract anywhere (e.g. `C:\fbac`).
3. Double-click **`START.bat`**. That's it.
   - On first run it auto-installs everything (1-3 min).
   - On subsequent runs it just starts the servers.
   - Two console windows open (backend + frontend) and your browser
     navigates to `http://localhost:5173`.
4. On first launch pick a **username and password** — stored locally in
   `backend/data/fb_ads_controller.db`.
5. Sign in, go to **FB Accounts**, click **Connect token**. Paste a
   long-lived FB user access token with the scopes:
   `ads_management`, `ads_read`, `business_management`, `read_insights`.

To stop the app, close both console windows.

### Updating to the latest version

Double-click **`UPDATE.bat`**. It downloads the latest `main.zip` from
GitHub, copies it over (preserving your venv, node_modules, and
database), reinstalls any new dependencies, and restarts the app. No
git, no PowerShell, no terminal.

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
├─ START.bat           # one-click launcher (Windows)
├─ UPDATE.bat          # one-click update from GitHub (Windows)
├─ setup.bat           # first-time install (Windows, called by START)
└─ run.sh              # one-click launcher (macOS / Linux)
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
