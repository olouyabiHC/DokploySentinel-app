# 🛡️ DokploySentinel

**Système d'Observabilité Centralisé, Surveillance Multi-Serveurs (Multi-VPS), Logs & Digest Périodique pour Dokploy.**

DokploySentinel est un microservice autonome et extensible composé de :
1. **Un Hub Central** (`DokploySentinel`) hébergé sur votre VPS principal (`https://sentinel.lekyn.com`), qui centralise les métriques, sondes Uptime/SSL et expédie les alertes et rapports sur **Telegram**, **Discord**, **WhatsApp** et **Email**.
2. **Des Sentinel-Agents Satellites** légers (< 30 Mo) déployés en 1 clic sur les VPS de vos clients ou vos autres serveurs Dokploy.

---

## 🌟 Fonctionnalités Principales

1. **Surveillance Multi-Serveurs (Multi-VPS & Multi-Clients) :**
   - Centralisation de tous vos serveurs VPS distants dans un seul groupe Telegram.
   - Suivi en direct du statut en ligne/hors-ligne de chaque serveur via **Heartbeat** avec alerte de signal perdu.
   - Suivi de la charge hôte (CPU %, RAM %, Espace Disque %).

2. **Surveillance des Logs & Formats Multiples :**
   - Écoute automatique des conteneurs via le socket Docker (`/var/run/docker.sock:ro`).
   - Parsing automatique des logs texte (Nginx, Traefik, Apache, Gunicorn, Uvicorn, Django) et **JSON structuré** (Winston, Pino, Structlog, Zap).
   - Détection des codes d'erreurs HTTP (`500`, `502`, `504`, `429`).
   - Détection des latences anormales et requêtes lentes (> 2000 ms).
   - Détection des traces d'erreurs critiques (`Traceback`, `Fatal error`, `panic`, `OOMKilled`, échecs DB).

3. **Sondes Uptime Externes & Validité SSL :**
   - Test périodique (toutes les 60s) des URLs publiques des sites clients.
   - Mesure de disponibilité (UP/DOWN) et de latence.
   - Surveillance proactive des certificats SSL (alerte si expiration < 7 jours).

4. **Alertes Immédiates & Protection Anti-Spam :**
   - Notification instantanée en cas de crash (`die`), dépassement de mémoire (`oom`), conteneur `unhealthy` ou exception critique.
   - Système de cooldown configurable (`ALERT_COOLDOWN_SECONDS`) pour éviter d'être submergé en cas de crash loop.

5. **Rapport de Santé Périodique (Digest toutes les 2h ou 3h) :**
   - Synthèse consolidée regroupée par serveur VPS envoyée automatiquement sur Telegram / Discord / WhatsApp / Email.
   - Indicateurs visuels : 🟢 Nominal, 🟡 Avertissement (latence/4xx), 🔴 Critique (5xx/crashes/OOM).

---

## 📁 Architecture du Projet

```
DokploySentinel/
├── src/                           # 🛡️ CODE DU HUB CENTRAL
│   ├── analyzers/
│   │   ├── log_parser.py          # Analyseur de logs (HTTP texte, JSON, exceptions)
│   │   └── metrics_aggregator.py  # Agrégateur des métriques multi-serveurs & ressources
│   ├── collectors/
│   │   ├── docker_collector.py    # Collecteur d'événements Docker local
│   │   └── uptime_prober.py       # Sonde Uptime HTTP et certificats SSL
│   ├── notifiers/
│   │   ├── dispatcher.py          # Routage d'alertes multi-serveurs & anti-spam
│   │   ├── telegram.py            # Notifier Telegram Bot (HTML sécurisé)
│   │   ├── discord.py             # Notifier Discord Webhook (Rich Embeds colorés)
│   │   ├── whatsapp.py            # Notifier WhatsApp (Evolution API / Webhook)
│   │   └── email.py               # Notifier Email SMTP (Modèles HTML responsive)
│   ├── scheduler/
│   │   └── digest_job.py          # Planificateur périodique & surveillance Heartbeat
│   ├── api/
│   │   └── webhooks.py            # Endpoints API (/agent/sync, /servers, /uptime, etc.)
│   ├── config.py                  # Configuration Pydantic Settings
│   └── main.py                    # Point d'entrée FastAPI
├── agent/                         # 🛰️ CODE DU SENTINEL-AGENT POUR VPS CLIENTS
│   ├── agent.py                   # Script de collecte local et expédition sécurisée
│   ├── Dockerfile                 # Image Docker ultra-légère Alpine (< 30 Mo)
│   ├── docker-compose.agent.yml   # Déploiement 1-clic pour Dokploy distant
│   ├── requirements.txt           # Dépendances minimales
│   └── .env.agent.example         # Modèle de configuration pour VPS client
├── tests/                         # Suite de 25 tests unitaires automatisés
├── pytest.ini                     # Configuration Pytest
├── Dockerfile                     # Image Docker du Hub
├── docker-compose.yml             # Déploiement 1-clic du Hub
└── requirements.txt               # Dépendances Python du Hub
```

---

## 🛰️ Déployer le Sentinel-Agent sur un VPS Client (en 1 minute)

Sur le Dokploy de n'importe quel VPS distant :

1. Créez une nouvelle application de type **Compose** (ou **Application**).
2. Utilisez le fichier [`agent/docker-compose.agent.yml`](file:///f:/LEKYN/CLIENTS/DokploySentinel/agent/docker-compose.agent.yml) ou montez le volume `/var/run/docker.sock:/var/run/docker.sock:ro`.
3. Renseignez les variables d'environnement dans Dokploy :
   ```env
   SENTINEL_HUB_URL=https://sentinel.lekyn.com
   SENTINEL_API_KEY=dokploy-sentinel-secret-2026-secure-key
   SERVER_NAME=VPS-Client-AutoEcole
   ```
4. Cliquez sur **Deploy**. L'agent commence immédiatement à synchroniser le VPS avec votre Hub central !

---

## 🧪 Lancer la Suite de Tests

```bash
.venv\Scripts\pytest.exe -v
```
