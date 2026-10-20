# LinkPulse

A URL shortener with built-in click analytics. Create short links with optional rules (alias, expiry date, click limit), share them, and see how they perform on a dashboard.

**Live demo:** _add your deployed link here_

## Features

- Shorten long URLs with an auto-generated code or a custom alias
- Link rules: expiry date and click limit, enforced on every visit
- Redirect handling with an "unavailable" page for expired or maxed-out links
- Click logging: timestamp, referrer, device, browser, IP
- Per-link analytics: total clicks, unique visitors, clicks over the last 7 days, and device, browser, and traffic-source breakdowns
- JSON API for creating links and fetching stats

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python, Flask, Flask-SQLAlchemy |
| Database | SQLite (local), PostgreSQL (production) |
| Frontend | HTML, CSS, Jinja templates |
| Charts | Chart.js |
| Server | Gunicorn |

## How it works

1. The user submits a long URL (plus optional alias, expiry, click limit).
2. The backend validates the URL, checks the alias is unique, applies the rules, and generates a short code.
3. The link is stored in the database and the short URL is returned.
4. When someone opens the short link, the app checks the link is active, not expired, and under its click limit, then redirects (HTTP 302).
5. Each redirect is logged as a click event.
6. The analytics page aggregates click events into stats and charts.

## Project structure

```
linkpulse/
├── app.py              # models, validation, routes
├── requirements.txt
├── Procfile            # for deployment (gunicorn)
├── static/
│   └── style.css
└── templates/
    ├── base.html
    ├── index.html      # create form + links table
    ├── stats.html      # per-link analytics
    └── error.html      # expired / limit reached page
```

## Run locally

```bash
git clone <your-repo-url>
cd linkpulse
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. A local SQLite database (`instance/linkpulse.db`) is created automatically.

## Routes

| Method | Route | Description |
|---|---|---|
| GET / POST | `/` | Create form, links table |
| GET | `/<code>` | Validate rules, log click, redirect |
| GET | `/stats/<code>` | Analytics page for a link |
| POST | `/api/links` | Create a link (JSON) |
| GET | `/api/links/<code>/stats` | Analytics data (JSON) |

**Create a link via API**

```bash
curl -X POST http://127.0.0.1:5000/api/links \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/long/page", "alias": "demo", "expiry_date": "2026-12-31", "click_limit": 100}'
```

`alias`, `expiry_date`, and `click_limit` are optional.

## Database schema

```
Link:  id, short_code (unique), original_url, expiry_date, click_limit,
       click_count, is_active, created_at
Click: id, link_id -> Link.id, clicked_at, referrer, device, browser, ip
```

## Deployment (Render)

1. Push this repo to GitHub.
2. Create a new **Web Service** on Render and connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Create a free **PostgreSQL** database on Render and set its URL as the `DATABASE_URL` environment variable.

Without `DATABASE_URL`, the app uses SQLite, which is wiped on restarts on most free hosts.

## Limitations

- No user accounts, so all links are visible on the home page
- No location tracking
- Unique visitors are counted by IP address
- Click limit checks are not safe against simultaneous requests (fine for a prototype)

## Possible next steps

User accounts, password-protected links, QR codes, bulk CSV import, campaigns and tags, and admin controls.
