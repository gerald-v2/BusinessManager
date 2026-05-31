# BizManager

A full-featured business management web app built with Flask.

## Features
- Multi-business management
- Point of Sale (POS)
- Finance & cost tracking
- CRM with loyalty points
- Employee & payroll management
- Attendance tracking
- Leave management
- AI-powered marketing tools

## Deployment

### Option A — Render.com (Recommended, free tier)
1. Push this folder to a GitHub repo
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your repo, Render detects `render.yaml` automatically
4. Add environment variable: `ANTHROPIC_API_KEY` = your key (optional, demo mode works without it)
5. Deploy!

### Option B — Netlify (via Functions)
1. Push to GitHub
2. Connect to Netlify
3. Build command: `pip install -r requirements.txt --target netlify/functions/packages && cp -r *.py *.json static templates netlify/functions/`
4. Add env var `ANTHROPIC_API_KEY` in Netlify Dashboard → Site Settings → Environment Variables

### Option C — Any PaaS (Railway, Fly.io, Heroku)
```bash
gunicorn app:app
```

## AI Marketing Tools
The marketing tab uses Claude AI. To enable it:
- Set `ANTHROPIC_API_KEY` environment variable
- Without it, demo-mode responses are shown so the app still works

## Default Login
On first launch, a default `admin` account is created automatically:
- Username: `admin`
- Password: `admin123` (or set via `ADMIN_PASSWORD` environment variable)

⚠️ **Change the admin password immediately after first login** via Admin → Accounts.
