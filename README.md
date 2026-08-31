# 🛡️ DokploySentinel 2.0

**Copilote DevOps & Système d'Observabilité Centralisé Intelligent pour Dokploy.**

DokploySentinel 2.0 transforme votre groupe Telegram en un **centre de contrôle interactif complet** propulsé par l'IA :
1. **Un Hub Central 2.0** (`DokploySentinel`) hébergé sur votre VPS principal (`https://sentinel.lekyn.com`), équipé d'un **Bot Telegram Interactif bidirectionnel**, d'un **gestionnaire de sourdines (Mutes)** et d'un **moteur de diagnostic IA (Smart RCA)**.
2. **Des Sentinel-Agents Satellites** légers (< 30 Mo) déployés en 1 clic sur les VPS de vos clients pour relayer métriques, logs et alertes en temps réel.

---

## 🌟 Nouvelles Fonctionnalités 2.0

### 1. 🤖 Bot Telegram Interactif & Commandes en Direct
Envoyez des commandes directement dans votre groupe Telegram :
- **`/status`** : Vue d'ensemble en direct de tous les VPS et de la santé globale.
- **`/servers`** : Liste des serveurs VPS connectés et charge hôte (CPU / RAM / Disque).
- **`/containers`** : Liste complète des conteneurs sous surveillance.
- **`/mute <motif> [durée]`** : Coupe instantanément les alertes d'un conteneur ou d'une techno sans toucher au serveur *(ex: `/mute wordpress 2h` ou `/mute all 30m`)*.
- **`/unmute <motif>`** : Réactive les alertes pour un motif.
- **`/mutes`** : Affiche les sourdines actuellement actives et le temps restant.
- **`/logs <nom_conteneur>`** : Récupère les 25 dernières lignes de logs d'un conteneur en direct.
- **`/restart <nom_conteneur>`** : Redémarre un conteneur à distance depuis Telegram avec confirmation.
- **`/ai <nom_conteneur>`** : Lance un diagnostic intelligent par IA sur les dernières erreurs d'un projet.
- **`/digest`** : Déclenche manuellement l'envoi du rapport consolidé.
- **`/help`** : Affiche le menu interactif.

### 2. ⚡ Boutons d'Action Rapide sous chaque Alerte (Inline Keyboards)
Chaque alerte critique reçue sur Telegram propose des actions en 1 clic :
- `[ 🔇 Muter 2h ]` : Met en sourdine le conteneur concerné.
- `[ 📋 Derniers logs ]` : Extrait et affiche les logs récents.
- `[ 🔄 Redémarrer ]` : Demande confirmation et redémarre le conteneur défaillant.
- `[ 🧠 Diagnostic IA ]` : Analyse la stacktrace et affiche la cause et la solution.

### 3. 🧠 Diagnostic Intelligent par IA (Smart Root-Cause Analysis)
- Analyse et contextualisation des erreurs (scans de bots WordPress, saturation OOM, pannes DB PostgreSQL/Redis, exceptions Django/Node).
- Traduction en français clair : **Cause exacte**, **Impact**, **Action recommandée**.

---

## 📁 Architecture du Projet

```
DokploySentinel/
├── src/                           # 🛡️ CODE DU HUB CENTRAL 2.0
│   ├── analyzers/
│   │   ├── log_parser.py          # Analyseur de logs (HTTP texte, JSON, exceptions)
│   │   └── metrics_aggregator.py  # Agrégateur des métriques multi-serveurs & ressources
│   ├── collectors/
│   │   ├── docker_collector.py    # Collecteur Docker non-bloquant
│   │   └── uptime_prober.py       # Sonde Uptime HTTP et certificats SSL
│   ├── notifiers/
│   │   ├── dispatcher.py          # Routage multi-serveurs & boutons interactifs
│   │   ├── telegram.py            # Notifier Telegram Bot (HTML, Webhook & Keyboards)
│   │   ├── discord.py             # Notifier Discord Webhook (Rich Embeds)
│   │   ├── whatsapp.py            # Notifier WhatsApp (Evolution API / Webhook)
│   │   └── email.py               # Notifier Email SMTP (HTML responsive)
│   ├── services/
│   │   ├── mutes_manager.py       # Gestionnaire dynamique des sourdines (persistant)
│   │   ├── ai_analyzer.py         # Moteur de diagnostic intelligent (Gemini & Heuristique)
│   │   └── telegram_bot_handler.py# Cerveau interactif (Commandes & Callbacks)
│   ├── scheduler/
│   │   └── digest_job.py          # Planificateur périodique & Heartbeats
│   ├── api/
│   │   └── webhooks.py            # Endpoints API (/telegram/webhook, /mutes, /ai, /agent/sync)
│   ├── config.py                  # Configuration Pydantic Settings
│   └── main.py                    # Point d'entrée FastAPI
├── agent/                         # 🛰️ CODE DU SENTINEL-AGENT POUR VPS CLIENTS
│   ├── agent.py                   # Micro-agent autonome pour VPS distant
│   ├── Dockerfile                 # Image Docker Alpine (< 30 Mo)
│   ├── docker-compose.agent.yml   # Déploiement 1-clic pour Dokploy distant
│   ├── requirements.txt           # Dépendances minimales
│   └── .env.agent.example         # Modèle de configuration pour VPS client
├── tests/                         # Suite complète de 39 tests unitaires automatisés
├── pytest.ini                     # Configuration Pytest
├── Dockerfile                     # Image Docker du Hub
├── docker-compose.yml             # Déploiement 1-clic du Hub
└── requirements.txt               # Dépendances Python du Hub
```

---

## 🛰️ Déployer le Sentinel-Agent sur un VPS Client

Sur le Dokploy de n'importe quel VPS distant :

1. Créez un nouveau service **Application** avec le dépôt GitHub `olouyabiHC/DokploySentinel-app` (branche `main`).
2. Type de build : `Dockerfile` (Context: `agent`, Dockerfile: `agent/Dockerfile`).
3. Volume : `/var/run/docker.sock:/var/run/docker.sock:ro`.
4. Variables d'environnement :
   ```env
   SENTINEL_HUB_URL=https://sentinel.lekyn.com
   SENTINEL_API_KEY=dokploy-sentinel-secret-2026-secure-key
   SERVER_NAME=VPS-Client-Nom
   ```
5. Cliquez sur **Deploy**.

---

## 🧪 Lancer la Suite de Tests

```bash
.venv\Scripts\pytest.exe -v
```
