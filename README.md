# 🛡️ DokploySentinel

**Système d'Observabilité Centralisé, Surveillance des Logs & Digest Périodique pour Applications Dokploy.**

DokploySentinel est un microservice autonome conçu pour surveiller en continu l'ensemble de vos conteneurs et plateformes déployés sur un serveur Dokploy / Docker.

---

## 🌟 Fonctionnalités Principales

1. **Surveillance des Logs & Formats Multiples :**
   - Écoute automatique des conteneurs via le socket Docker (`/var/run/docker.sock`).
   - Parsing automatique des formats texte (Nginx, Traefik, Apache, Gunicorn, Uvicorn, Django) et **JSON structuré** (Winston, Pino, Structlog, Zap).
   - Détection des codes d'erreurs HTTP (`500`, `502`, `504`, `429`).
   - Détection des latences anormales et requêtes lentes (> 2000 ms).
   - Détection des traces d'erreurs critiques (`Traceback`, `Fatal error`, `panic`, `OOMKilled`, échecs DB).

2. **Surveillance Proactive des Ressources (CPU & RAM) :**
   - Échantillonnage en direct de l'utilisation CPU et Mémoire par conteneur.
   - Alertes préventives en cas de saturation de RAM (> 90%) pour anticiper les OOM.
   - Suivi des statuts des healthchecks Docker (`healthy` / `unhealthy`).

3. **Alertes Immédiates & Protection Anti-Spam :**
   - Notification instantanée en cas de crash (`die`), dépassement de mémoire (`oom`), conteneur `unhealthy` ou exception critique.
   - Système de cooldown / anti-flood configurable (`ALERT_COOLDOWN_SECONDS`) pour éviter d'être submergé en cas de crash loop.

4. **Rapport de Santé Périodique (Digest toutes les 2h ou 3h) :**
   - Synthèse consolidée de tous vos projets envoyée automatiquement sur **Telegram**, **Discord**, **WhatsApp** et **Email (SMTP HTML)**.
   - Indicateurs visuels : 🟢 Nominal, 🟡 Avertissement (latence/4xx), 🔴 Critique (5xx/crashes/OOM).
   - Statistiques complètes : requêtes totales, taux de succès, latence médiane et p95, charge CPU & RAM.

5. **API REST & Ingestion Directe :**
   - `/api/v1/health` : Statut du service.
   - `/api/v1/stats` : Métriques consolidées en direct.
   - `/api/v1/containers` : État détaillé de tous les conteneurs surveillés.
   - `/api/v1/notifications/test` : Test immédiat de chaque canal de notification.
   - `/api/v1/logs/ingest` : Ingestion directe de logs applicatifs par HTTP.
   - `/api/v1/webhooks/dokploy` : Récepteur de notifications de déploiement Dokploy.
   - `/api/v1/digest/trigger` : Déclenchement manuel d'un digest.

---

## 📁 Architecture du Projet

```
DokploySentinel/
├── src/
│   ├── analyzers/
│   │   ├── log_parser.py          # Analyseur de logs (HTTP texte, JSON, exceptions)
│   │   └── metrics_aggregator.py  # Agrégateur des métriques, latences & ressources
│   ├── collectors/
│   │   └── docker_collector.py    # Collecteur d'événements Docker, stats CPU/RAM & logs
│   ├── notifiers/
│   │   ├── dispatcher.py          # Formattage multi-canal, routage & anti-spam
│   │   ├── telegram.py            # Notifier Telegram Bot (HTML sécurisé)
│   │   ├── discord.py             # Notifier Discord Webhook (Rich Embeds colorés)
│   │   ├── whatsapp.py            # Notifier WhatsApp (Evolution API / Webhook)
│   │   └── email.py               # Notifier Email SMTP (Modèles HTML responsive)
│   ├── scheduler/
│   │   └── digest_job.py          # Planificateur périodique (APScheduler)
│   ├── api/
│   │   └── webhooks.py            # Endpoints API, Ingestion, Tests & Dokploy Webhooks
│   ├── config.py                  # Configuration Pydantic Settings
│   └── main.py                    # Point d'entrée FastAPI
├── tests/                         # Suite de tests unitaires automatisés
├── pytest.ini                     # Configuration Pytest
├── Dockerfile                     # Image Docker optimisée
├── docker-compose.yml             # Déploiement 1-clic Dokploy
├── requirements.txt               # Dépendances Python
└── .env.example                   # Modèle de configuration des variables
```

---

## 🚀 Démarrage Rapide

### 1. Configuration Locale

```bash
# Accéder au dossier
cd F:\LEKYN\CLIENTS\DokploySentinel

# Créer et activer l'environnement virtuel
python -m venv .venv
.venv\Scripts\activate   # (Sur Windows) ou source .venv/bin/activate (Sur Linux)

# Installer les dépendances
pip install -r requirements.txt

# Créer votre fichier .env
cp .env.example .env

# Lancer l'application
uvicorn src.main:app --reload --port 8000
```

L'interface interactive Swagger est disponible sur : `http://localhost:8000/docs`

---

## 🚢 Déploiement sur Dokploy en Production

1. Dans Dokploy, créez une nouvelle application de type **Compose** ou **Dockerfile**.
2. Renseignez les variables d'environnement dans l'onglet **Environment** de Dokploy (copiez depuis `.env.example`).
3. Montez le volume du socket Docker en lecture seule :
   ```yaml
   volumes:
     - /var/run/docker.sock:/var/run/docker.sock:ro
   ```
4. Cliquez sur **Deploy**. DokploySentinel commence immédiatement à surveiller tous vos conteneurs !

---

## 🧪 Lancer la Suite de Tests

```bash
.venv\Scripts\pytest.exe -v
```
