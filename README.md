# 🛡️ DokploySentinel

**Système d'Observabilité Centralisé, Surveillance des Logs & Digest Périodique pour Applications Dokploy.**

DokploySentinel est un microservice autonome conçu pour surveiller en continu l'ensemble de vos conteneurs et plateformes déployés sur un serveur Dokploy / Docker.

---

## 🌟 Fonctionnalités Principales

1. **Surveillance des Logs en Temps Réel :**
   - Écoute automatique des conteneurs via le socket Docker (`/var/run/docker.sock`).
   - Détection des codes d'erreurs HTTP (`500`, `502`, `504`, `429`).
   - Détection des latences anormales et requêtes lentes (> 2000 ms).
   - Détection des traces d'erreurs critiques (`Traceback`, `Fatal error`, `panic`, `OOMKilled`).

2. **Alertes Immédiates en Temps Réel :**
   - Notification instantanée lors d'un crash de conteneur, dépassement de mémoire (OOM) ou exception critique.

3. **Rapport de Santé Périodique (Digest toutes les 2h ou 3h) :**
   - Synthèse consolidée de tous vos projets envoyée automatiquement sur **Telegram**, **Discord**, **WhatsApp** ou **Email**.
   - Indicateurs visuels : 🟢 Nominal, 🟡 Avertissement (latence/4xx), 🔴 Critique (5xx/crashes).
   - Statistiques complètes : requêtes totales, taux de succès, latence médiane et p95.

4. **Récepteur de Webhooks Dokploy :**
   - Endpoint `/api/v1/webhooks/dokploy` pour recevoir et relayer les notifications de déploiement Dokploy.

---

## 📁 Architecture du Projet

```
DokploySentinel/
├── src/
│   ├── analyzers/
│   │   ├── log_parser.py          # Analyseur de lignes de logs (HTTP, erreurs, latences)
│   │   └── metrics_aggregator.py  # Agrégateur des métriques par conteneur
│   ├── collectors/
│   │   └── docker_collector.py    # Collecteur d'événements et logs Docker Socket
│   ├── notifiers/
│   │   ├── dispatcher.py          # Formattage et routage des alertes/digests
│   │   ├── telegram.py            # Notifier Telegram Bot
│   │   └── discord.py             # Notifier Discord Webhook
│   ├── scheduler/
│   │   └── digest_job.py          # Planificateur périodique (APScheduler)
│   ├── api/
│   │   └── webhooks.py            # Endpoints Webhook, Health, Stats & Trigger manuel
│   ├── config.py                  # Configuration Pydantic Settings
│   └── main.py                    # Point d'entrée FastAPI
├── tests/                         # Tests unitaires automatisés
├── Dockerfile                     # Image Docker optimisée
├── docker-compose.yml             # Déploiement 1-clic Dokploy
├── requirements.txt               # Dépendances Python
└── .env.example                   # Exemple de configuration
```

---

## 🚀 Démarrage Rapide

### 1. Configuration Locale

```bash
# Cloner ou ouvrir le projet
cd F:\LEKYN\CLIENTS\DokploySentinel

# Créer l'environnement virtuel
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
3. Activez le volume de lecture seule pour le socket Docker :
   ```yaml
   volumes:
     - /var/run/docker.sock:/var/run/docker.sock:ro
   ```
4. Cliquez sur **Deploy**. DokploySentinel commence immédiatement à surveiller tous vos conteneurs !

---

## 🔔 Configuration des Notifications Telegram

1. Créez un bot via [@BotFather](https://t.me/BotFather) sur Telegram et récupérez le `TELEGRAM_BOT_TOKEN`.
2. Créez un canal ou groupe privé, ajoutez le bot en tant qu'administrateur.
3. Récupérez le `TELEGRAM_CHAT_ID` et renseignez-les dans `.env` :
   ```env
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   TELEGRAM_CHAT_ID=-1001234567890
   ```

---

## 🧪 Lancer les Tests

```bash
pytest tests/ -v
```
