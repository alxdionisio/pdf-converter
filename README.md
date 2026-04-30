# doc→pdf — Convertisseur local & confidentiel

Plateforme minimaliste d'auto-hébergement pour convertir des documents en PDF.  
Aucun fichier ne transite par un service tiers.

---

## Stack

| Couche | Techno |
|--------|--------|
| Frontend | React 18 + Vite |
| Backend | FastAPI (Python 3.12) |
| Conversion | LibreOffice headless + ImageMagick |
| Déploiement | Docker Compose |

---

## Formats supportés

`.docx` `.doc` `.odt` `.rtf` `.pptx` `.ppt` `.odp` `.xlsx` `.xls` `.ods` `.html` `.txt` `.csv` `.png` `.jpg` `.jpeg` `.gif` `.bmp` `.tiff` `.svg`

---

## Lancement (Docker)

```bash
# Build et démarrage
docker-compose up --build

# L'app est disponible sur http://localhost:3000
```

Pour changer le port, modifier `docker-compose.yml` → `"3000:80"`.

---

## Développement local (sans Docker)

### Backend
```bash
cd backend
pip install -r requirements.txt
# Installer LibreOffice : https://www.libreoffice.org/download/
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
# Le proxy Vite redirige /convert vers http://localhost:8000
```

---

## Déploiement sur serveur

1. Copier le projet sur votre serveur (SSH, git clone, etc.)
2. Installer Docker + Docker Compose
3. `docker-compose up -d --build`
4. Optionnel : mettre un reverse proxy Nginx/Caddy devant avec HTTPS

### Exemple Caddy (HTTPS automatique)
```
converter.mondomaine.fr {
    reverse_proxy localhost:3000
}
```

---

## Configuration

| Variable | Description | Défaut |
|----------|-------------|--------|
| Port exposé | Modifier dans `docker-compose.yml` | `3000` |
| Taille max upload | Modifier dans `nginx.conf` (`client_max_body_size`) | `100M` |
| Timeout conversion | Modifier dans `nginx.conf` (`proxy_read_timeout`) | `120s` |

---

## Architecture

```
Request flow:
Browser → Nginx (port 3000)
         ├── /convert  → backend:8000 (FastAPI)
         │              └── LibreOffice/ImageMagick → PDF
         └── /*        → React SPA (dist/)
```

Le backend n'est jamais exposé directement sur internet.
