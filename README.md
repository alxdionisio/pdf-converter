# doc→pdf — Self-hosted, private document-to-PDF converter

Convert documents to PDF on your own machine or server. Files never go through a
third-party service, and nothing is kept after the conversion.

🇫🇷 [Version française](README.fr.md) — the interface itself is in French.

## Supported formats

`.docx` `.doc` `.odt` `.rtf` `.pptx` `.ppt` `.odp` `.xlsx` `.xls` `.ods` `.html` `.htm` `.txt` `.csv` `.png` `.jpg` `.jpeg` `.gif` `.bmp` `.tiff` `.svg`

## Quick start (Docker)

Requires Docker with Compose v2.

```bash
git clone <this repository> && cd pdf-converter
cp backend/.env.example backend/.env

# 1. Create an account: prints a "login:salt:hash" line
docker compose run --build --rm --no-deps backend python hash_password.py you@example.com

# 2. Generate a signing secret
openssl rand -hex 32

# 3. Paste both into backend/.env (AUTH_USERS and AUTH_TOKEN_SECRET), then:
docker compose up --build -d
```

Open <http://localhost:3002> and sign in.

The backend refuses to start while `AUTH_USERS` or `AUTH_TOKEN_SECRET` is empty or still a
placeholder. Add more accounts by separating entries with commas in `AUTH_USERS`.

## Configuration

| Setting | Where | Default |
|---------|-------|---------|
| Accounts | `AUTH_USERS` in `backend/.env` | required |
| Token signing secret | `AUTH_TOKEN_SECRET` in `backend/.env` | required |
| Session lifetime | `AUTH_TOKEN_TTL_SECONDS` in `backend/.env` | `28800` (8 h) |
| Allowed origins, only with a separate API domain | `CORS_ORIGINS` in `backend/.env` | none |
| Listening address | `BIND_ADDRESS` (shell or root `.env`) | `127.0.0.1` |
| Port | `PORT` (shell or root `.env`) | `3002` |
| Max upload size | `client_max_body_size` in `frontend/nginx.conf` and `MAX_UPLOAD_SIZE` in `backend/main.py` | 100 MB |
| Simultaneous conversions | `MAX_CONCURRENT_CONVERSIONS` in `backend/main.py` | `2` |
| API base URL, only with a separate API domain | `VITE_API_URL` build argument of the frontend image | same origin |

## Deploying on a server

The app listens on `127.0.0.1` only and does not provide TLS. Put an HTTPS reverse proxy in
front of it. Example with Caddy (automatic certificates):

```
converter.example.com {
    reverse_proxy localhost:3002
}
```

To expose it directly on a trusted network, start it with `BIND_ADDRESS=0.0.0.0`.

## Security

- Sign-in is required to convert. Passwords are stored as salted scrypt hashes.
- Login is limited to 5 attempts per minute per IP, conversions to 20 per minute.
- Uploads from anonymous clients are rejected before the file is read.
- The backend container has no outbound network access, runs as an unprivileged user and
  has CPU, memory and process limits.
- Fonts are bundled: the browser makes no request outside your server.

Give accounts only to people you trust, and read [SECURITY.md](SECURITY.md) for the threat
model and how to report a vulnerability.

## Local development (without Docker)

Requires Python 3.12, Node 22, [LibreOffice](https://www.libreoffice.org/download/) and ImageMagick.

```bash
# Backend — main.py reads environment variables, not the .env file
cd backend
pip install -r requirements.txt -r requirements-dev.txt
set -a; source .env; set +a
uvicorn main:app --reload --port 8000
pytest && ruff check .

# Frontend — http://localhost:5173, proxies /convert, /auth and /health to the backend
cd frontend
npm install
npm run dev
```

## Architecture

```
Browser → nginx (port 3002)
          ├── /auth/login → backend:8000 (FastAPI)
          ├── /convert    → backend:8000 → LibreOffice / ImageMagick → PDF
          ├── /health     → backend:8000
          └── /*          → React SPA
```

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + Vite, served by nginx |
| Backend | FastAPI (Python 3.12) |
| Conversion | LibreOffice headless + ImageMagick |
| Deployment | Docker Compose |

## License

[MIT](LICENSE)
