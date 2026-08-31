"""AI Root-Cause Analysis (Smart RCA) & Diagnostic Engine for DokploySentinel."""

import logging
import re
from typing import Dict, Optional
import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """Moteur d'analyse intelligente des pannes, stacktraces et scans de robots."""

    @staticmethod
    async def analyze_incident(
        container_name: str,
        reason: str,
        details: str = "",
        server_name: str = "",
    ) -> Dict[str, str]:
        """Analyse un incident et retourne un diagnostic en français structuré."""
        # 1. Si une clé API Gemini ou OpenAI est configurée, interroger le LLM
        api_key = settings.gemini_api_key or settings.ai_api_key
        if settings.ai_analysis_enabled and api_key:
            try:
                llm_result = await AIAnalyzer._query_gemini(
                    container_name=container_name,
                    reason=reason,
                    details=details,
                    server_name=server_name,
                    api_key=api_key,
                )
                if llm_result:
                    return llm_result
            except Exception as e:
                logger.warning(f"[AIAnalyzer] Erreur lors de l'appel Gemini LLM : {e}. Utilisation du moteur heuristique.")

        # 2. Moteur Heuristique Expert (Offline, instantané et sans coût d'API)
        return AIAnalyzer._heuristic_analysis(container_name, reason, details, server_name)

    @staticmethod
    async def _query_gemini(
        container_name: str,
        reason: str,
        details: str,
        server_name: str,
        api_key: str,
    ) -> Optional[Dict[str, str]]:
        """Interroge Gemini pour un diagnostic IA approfondi."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = (
            "Tu es un expert DevOps et SRE d'élite. Analyse l'incident suivant survenu sur un conteneur Docker et fournis un diagnostic concis en français.\n\n"
            f"Serveur: {server_name}\n"
            f"Conteneur: {container_name}\n"
            f"Incident: {reason}\n"
            f"Détails / Logs:\n{details[:1500]}\n\n"
            "Format attendu (réponds STRICTEMENT sous ce format avec ces puces) :\n"
            "• Cause : <explication claire de l'origine exacte>\n"
            "• Impact : <impact sur les utilisateurs ou le service>\n"
            "• Action Recommandée : <solution technique concrète pour réparer ou bloquer>\n"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if text.strip():
                        return {
                            "source": "Gemini AI",
                            "formatted_text": text.strip(),
                            "category": "AI_DIAGNOSIS",
                        }
        return None

    @staticmethod
    def _heuristic_analysis(
        container_name: str,
        reason: str,
        details: str,
        server_name: str,
    ) -> Dict[str, str]:
        """Moteur d'intelligence heuristique offline basé sur les motifs de pannes réelles."""
        c_lower = container_name.lower()
        d_lower = details.lower()
        r_lower = reason.lower()

        # 1. Attaque de bot / Scanner de vulnérabilité WordPress
        if any(w in d_lower for w in ["abspath", "wp-settings.php", "compat-utf8", "wp-admin", "wp-includes", "flatsome", "get_header()", "get_locale()"]) or "wordpress" in c_lower:
            return {
                "source": "Sentinel Heuristic Engine",
                "category": "BOT_SCANNER",
                "formatted_text": (
                    "• <b>Cause :</b> Scan automatisé de robot / pirate cherchant à exécuter directement des scripts PHP internes de WordPress.\n"
                    "• <b>Impact :</b> Pollution des logs d'erreurs 500 et consommation inutile de ressources CPU/RAM sur le serveur.\n"
                    "• <b>Action Recommandée :</b> Mettre en place <b>Cloudflare WAF (Bot Fight Mode)</b> pour filtrer les scanners en amont, ou bloquer l'accès direct aux fichiers <code>.php</code> dans les règles Traefik / Nginx."
                ),
            }

        # 2. Saturation Mémoire / Out Of Memory (OOMKilled)
        if "oom" in r_lower or "137" in r_lower or "out of memory" in d_lower:
            return {
                "source": "Sentinel Heuristic Engine",
                "category": "MEMORY_OOM",
                "formatted_text": (
                    "• <b>Cause :</b> Dépassement de la limite de mémoire RAM allouée au conteneur (le noyau Linux a tué le processus via OOMKiller).\n"
                    "• <b>Impact :</b> Arrêt brutal et interruption temporaire du service pour les utilisateurs.\n"
                    "• <b>Action Recommandée :</b> Augmenter la limite RAM du conteneur dans Dokploy, ou auditer le code pour identifier une fuite de mémoire (memory leak) ou un traitement de fichier trop volumineux en mémoire."
                ),
            }

        # 3. Échec de connexion Base de Données (PostgreSQL / MySQL / Redis)
        if any(w in d_lower for w in ["connection refused", "password authentication failed", "too many connections", "pg_hba.conf", "operationalerror", "can't connect to mysql", "redis.exceptions.connectionerror"]):
            return {
                "source": "Sentinel Heuristic Engine",
                "category": "DATABASE_ERROR",
                "formatted_text": (
                    "• <b>Cause :</b> Impossible d'établir la connexion avec le serveur de base de données (PostgreSQL, MySQL ou Redis).\n"
                    "• <b>Impact :</b> Échec des requêtes métiers, erreurs 500 sur les endpoints d'API et blocage des transactions.\n"
                    "• <b>Action Recommandée :</b> Vérifier que le conteneur de base de données est bien <code>running</code>, contrôler les identifiants dans les variables d'environnement, et vérifier que le pool PgBouncer n'est pas saturé."
                ),
            }

        # 4. Erreur Python / Django / FastAPI
        if "traceback" in d_lower or "exception" in d_lower or "django" in c_lower:
            # Recherche de la dernière ligne d'exception (ex: ValueError, KeyError, etc.)
            exc_match = re.findall(r"([A-Za-z_]+Error: .+)", details)
            exc_summary = exc_match[-1] if exc_match else "Exception non gérée dans le code Python."
            return {
                "source": "Sentinel Heuristic Engine",
                "category": "PYTHON_EXCEPTION",
                "formatted_text": (
                    f"• <b>Cause :</b> {exc_summary}\n"
                    "• <b>Impact :</b> La requête HTTP ou la tâche d'arrière-plan s'est interrompue avec un code d'erreur 500.\n"
                    "• <b>Action Recommandée :</b> Vérifier la stacktrace ci-dessus pour corriger le bug dans la vue ou le service concerné, et ajouter une gestion d'exception (<code>try/except</code>)."
                ),
            }

        # 5. Erreur Node.js / JavaScript
        if any(w in d_lower for w in ["unhandledrejection", "cannot find module", "typeerror", "referenceerror", "econnrefused"]):
            return {
                "source": "Sentinel Heuristic Engine",
                "category": "NODEJS_EXCEPTION",
                "formatted_text": (
                    "• <b>Cause :</b> Exception JavaScript non interceptée ou promesse rejetée (Unhandled Promise Rejection).\n"
                    "• <b>Impact :</b> Possibilité de crash du worker Node.js ou de blocage de l'Event Loop.\n"
                    "• <b>Action Recommandée :</b> Vérifier les modules importés dans <code>package.json</code> et ajouter des blocs <code>.catch()</code> ou <code>try/catch</code> autour des appels asynchrones."
                ),
            }

        # 6. Échec Healthcheck Docker
        if "unhealthy" in r_lower:
            return {
                "source": "Sentinel Heuristic Engine",
                "category": "HEALTHCHECK_FAILED",
                "formatted_text": (
                    "• <b>Cause :</b> La commande de vérification de santé (Docker Healthcheck) a échoué plusieurs fois consécutives.\n"
                    "• <b>Impact :</b> Le conteneur ne répond plus correctement aux requêtes HTTP ou est en état de blocage interne (Deadlock).\n"
                    "• <b>Action Recommandée :</b> Vérifier la sonde de santé dans le Dockerfile / compose, contrôler les logs récents pour voir si le port d'écoute répond, ou redémarrer le conteneur."
                ),
            }

        # Défaut générique
        return {
            "source": "Sentinel Heuristic Engine",
            "category": "GENERIC_ALERT",
            "formatted_text": (
                f"• <b>Cause :</b> Anomalie détectée : {reason}.\n"
                "• <b>Impact :</b> Dysfonctionnement partiel ou arrêt du conteneur.\n"
                "• <b>Action Recommandée :</b> Consulter les logs complets du conteneur pour analyser le contexte avant l'incident."
            ),
        }


ai_analyzer = AIAnalyzer()
