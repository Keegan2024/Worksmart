# Worksmart (Flask) - Preloaded demo

This is a ready-to-deploy Flask application for the *Worksmart* ART tracker. It comes preloaded with sample data
so you can test multi-user behaviour locally and on Koyeb after replacing the `DATABASE_URL` env var.

## Quick start (local)

1. (Optional) Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and edit `SECRET_KEY` (and DATABASE_URL if you have Postgres).
4. Run the app:
   ```bash
   flask run
   ```
   Or for production locally:
   ```bash
   gunicorn -b 127.0.0.1:8000 app:app
   ```

## Deploy to Koyeb
1. Push this repo to GitHub.
2. On Koyeb create a service connected to the repo and set environment vars:
   - SECRET_KEY
   - DATABASE_URL (your PostgreSQL database URI)
   - SEED_DATA = 1 (optional, seeds sample data)
3. Deploy.

## Default demo user accounts (pre-seeded)
- admin / admin123  (system_admin)
- pc001 / pc123      (professional_counselor)
- lc001 / lc123      (lay_counselor)
- cl001 / cl123      (clinician)

## Notes
- The project defaults to SQLite for local testing if no DATABASE_URL is provided.
- Replace DATABASE_URL before deploying to production.
