# doc→pdf — Convertisseur local et confidentiel

Convertissez vos documents en PDF sur votre propre machine ou serveur. Les fichiers ne
passent par aucun service tiers, et rien n'est conservé après la conversion.

🇬🇧 [English version](README.md)

## Formats supportés

`.docx` `.doc` `.odt` `.rtf` `.pptx` `.ppt` `.odp` `.xlsx` `.xls` `.ods` `.html` `.htm` `.txt` `.csv` `.png` `.jpg` `.jpeg` `.gif` `.bmp` `.tiff` `.svg`

## Démarrage rapide (Docker)

Nécessite Docker avec Compose v2.

```bash
git clone <ce dépôt> && cd pdf-converter
cp backend/.env.example backend/.env

# 1. Créer un compte : affiche une ligne "login:sel:hash"
docker compose run --build --rm --no-deps backend python hash_password.py vous@example.com

# 2. Générer un secret de signature
openssl rand -hex 32

# 3. Coller les deux dans backend/.env (AUTH_USERS et AUTH_TOKEN_SECRET), puis :
docker compose up --build -d
```

Ouvrez <http://localhost:3002> et connectez-vous.

Le backend refuse de démarrer tant que `AUTH_USERS` ou `AUTH_TOKEN_SECRET` est vide ou
contient encore une valeur d'exemple. Pour plusieurs comptes, séparez les entrées par des
virgules dans `AUTH_USERS`.

## Configuration

| Réglage | Où | Défaut |
|---------|----|--------|
| Comptes | `AUTH_USERS` dans `backend/.env` | requis |
| Secret de signature des tokens | `AUTH_TOKEN_SECRET` dans `backend/.env` | requis |
| Durée de session | `AUTH_TOKEN_TTL_SECONDS` dans `backend/.env` | `28800` (8 h) |
| Origines autorisées, seulement si l'API a son propre domaine | `CORS_ORIGINS` dans `backend/.env` | aucune |
| Adresse d'écoute | `BIND_ADDRESS` (shell ou `.env` à la racine) | `127.0.0.1` |
| Port | `PORT` (shell ou `.env` à la racine) | `3002` |
| Taille max d'envoi | `client_max_body_size` dans `frontend/nginx.conf` et `MAX_UPLOAD_SIZE` dans `backend/main.py` | 100 Mo |
| Conversions simultanées | `MAX_CONCURRENT_CONVERSIONS` dans `backend/main.py` | `2` |
| URL de l'API, seulement si elle a son propre domaine | argument de build `VITE_API_URL` de l'image frontend | même origine |

## Déploiement sur un serveur

L'application n'écoute que sur `127.0.0.1` et ne fournit pas de TLS. Placez un reverse proxy
HTTPS devant. Exemple avec Caddy (certificats automatiques) :

```
converter.example.com {
    reverse_proxy localhost:3002
}
```

Pour l'exposer directement sur un réseau de confiance, lancez-la avec `BIND_ADDRESS=0.0.0.0`.

## Sécurité

- La connexion est obligatoire pour convertir. Les mots de passe sont stockés sous forme de
  hash scrypt avec sel.
- La connexion est limitée à 5 tentatives par minute et par IP, les conversions à 20 par minute.
- Les envois de clients anonymes sont rejetés avant la lecture du fichier.
- Le conteneur backend n'a aucun accès réseau sortant, tourne avec un utilisateur non
  privilégié et a des limites de CPU, de mémoire et de processus.
- Les polices sont embarquées : le navigateur ne fait aucune requête hors de votre serveur.

Ne donnez des comptes qu'à des personnes de confiance, et lisez [SECURITY.md](SECURITY.md)
pour le modèle de menace et le signalement d'une vulnérabilité.

## Développement local (sans Docker)

Nécessite Python 3.12, Node 22, [LibreOffice](https://www.libreoffice.org/download/) et ImageMagick.

```bash
# Backend — main.py lit les variables d'environnement, pas le fichier .env
cd backend
pip install -r requirements.txt -r requirements-dev.txt
set -a; source .env; set +a
uvicorn main:app --reload --port 8000
pytest && ruff check .

# Frontend — http://localhost:5173, redirige /convert, /auth et /health vers le backend
cd frontend
npm install
npm run dev
```

## Architecture

```
Navigateur → nginx (port 3002)
             ├── /auth/login → backend:8000 (FastAPI)
             ├── /convert    → backend:8000 → LibreOffice / ImageMagick → PDF
             ├── /health     → backend:8000
             └── /*          → SPA React
```

| Couche | Techno |
|--------|--------|
| Frontend | React 18 + Vite, servi par nginx |
| Backend | FastAPI (Python 3.12) |
| Conversion | LibreOffice headless + ImageMagick |
| Déploiement | Docker Compose |

## Licence

[MIT](LICENSE)
