"""Log parser for extracting HTTP status, latencies, JSON logs, and critical exceptions from container logs."""

import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedLogEntry:
    raw_line: str
    container_name: str
    is_http_request: bool = False
    http_method: Optional[str] = None
    http_path: Optional[str] = None
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    is_error: bool = False
    is_critical_exception: bool = False
    error_message: Optional[str] = None


class LogParser:
    # 1. Regex pour logs d'accès HTTP texte standards (Nginx, Traefik, Gunicorn, Apache, Caddy, Uvicorn)
    # Ex standard: '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "POST /path/ HTTP/1.1" 200 122 "ref" "ua" 80202'
    # Ex uvicorn: 'INFO: 127.0.0.1:54321 - "GET /api/v1/health HTTP/1.1" 200 OK 12.5ms'
    HTTP_ACCESS_REGEX = re.compile(
        r'"(?P<method>[A-Z]+)\s+(?P<path>[^\s]+)\s+HTTP/[0-9.]+"\s+(?P<status>\d{3})\b.*?(?:(?P<latency>\d+(?:\.\d+)?)\s*(?:ms|s|µs)?)?$',
        re.IGNORECASE,
    )

    # Regex spécifique Uvicorn avec durée en secondes / ms à la fin
    UVICORN_REGEX = re.compile(
        r'"(?P<method>[A-Z]+)\s+(?P<path>[^\s]+)\s+HTTP/[0-9.]+"\s+(?P<status>\d{3})(?:\s+[A-Za-z ]+)?(?:\s*-\s*(?P<latency>\d+(?:\.\d+)?)(?P<unit>ms|s)?)?'
    )

    # 2. Patterns d'erreurs critiques multi-langages
    CRITICAL_PATTERNS = [
        re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
        re.compile(r"Internal Server Error", re.IGNORECASE),
        re.compile(r"Fatal error:", re.IGNORECASE),
        re.compile(r"Uncaught Exception:", re.IGNORECASE),
        re.compile(r"UnhandledPromiseRejectionWarning:", re.IGNORECASE),
        re.compile(r"Unhandled rejection", re.IGNORECASE),
        re.compile(r"panic:", re.IGNORECASE),
        re.compile(r"thread '.*' panicked at", re.IGNORECASE),
        re.compile(r"OOMKilled|Out of memory", re.IGNORECASE),
        re.compile(r"DatabaseError|OperationalError|ConnectionRefusedError|MongoNetworkError|RedisConnectionError", re.IGNORECASE),
        re.compile(r"\[CRITICAL\]|\[FATAL\]|\blevel=(?:critical|fatal|error)\b", re.IGNORECASE),
        re.compile(r"Exception in thread \".*\" java\.", re.IGNORECASE),
    ]

    @classmethod
    def parse_line(cls, line: str, container_name: str) -> ParsedLogEntry:
        line_clean = line.strip()
        entry = ParsedLogEntry(raw_line=line_clean, container_name=container_name)

        if not line_clean:
            return entry

        # ── 1. Tentative de parsing JSON structuré ─────────────────────────────
        if line_clean.startswith("{") and line_clean.endswith("}"):
            if cls._try_parse_json(line_clean, entry):
                return entry

        # ── 2. Parsing log HTTP texte standard ────────────────────────────────
        match = cls.HTTP_ACCESS_REGEX.search(line_clean)
        if match:
            entry.is_http_request = True
            entry.http_method = match.group("method").upper()
            entry.http_path = match.group("path")
            entry.status_code = int(match.group("status"))

            raw_lat = match.group("latency")
            if raw_lat:
                val = float(raw_lat)
                # Si valeur très grande (ex: 80202 microsecondes de gunicorn/nginx), convertir en ms
                if val > 10000:
                    entry.latency_ms = round(val / 1000.0, 2)
                else:
                    entry.latency_ms = round(val, 2)

            cls._evaluate_http_status(entry)
            return entry

        # ── 3. Parsing Uvicorn format alternatif ──────────────────────────────
        uvicorn_match = cls.UVICORN_REGEX.search(line_clean)
        if uvicorn_match:
            entry.is_http_request = True
            entry.http_method = uvicorn_match.group("method").upper()
            entry.http_path = uvicorn_match.group("path")
            entry.status_code = int(uvicorn_match.group("status"))

            raw_lat = uvicorn_match.group("latency")
            unit = uvicorn_match.group("unit") or "ms"
            if raw_lat:
                val = float(raw_lat)
                if unit == "s":
                    entry.latency_ms = round(val * 1000.0, 2)
                else:
                    entry.latency_ms = round(val, 2)

            cls._evaluate_http_status(entry)
            return entry

        # ── 4. Détection d'erreurs critiques dans les logs applicatifs ─────────
        for pattern in cls.CRITICAL_PATTERNS:
            if pattern.search(line_clean):
                entry.is_critical_exception = True
                entry.is_error = True
                entry.error_message = line_clean[:300]
                break

        return entry

    @classmethod
    def _try_parse_json(cls, line: str, entry: ParsedLogEntry) -> bool:
        """Tente de parser les logs structurés au format JSON."""
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return False

            # Détection HTTP dans JSON
            status = data.get("status") or data.get("statusCode") or data.get("status_code") or data.get("response_status")
            method = data.get("method") or data.get("http_method") or (data.get("req", {}).get("method") if isinstance(data.get("req"), dict) else None)
            path = data.get("path") or data.get("url") or data.get("route") or (data.get("req", {}).get("url") if isinstance(data.get("req"), dict) else None)
            latency = (
                data.get("latency_ms")
                or data.get("duration")
                or data.get("responseTime")
                or data.get("latency")
                or data.get("time_taken")
            )

            if status is not None and str(status).isdigit():
                entry.is_http_request = True
                entry.status_code = int(status)
                if method:
                    entry.http_method = str(method).upper()
                if path:
                    entry.http_path = str(path)
                if latency is not None:
                    try:
                        lat_val = float(latency)
                        # Si duration en secondes (ex: 0.052), convertir en ms
                        if lat_val < 1.0 and "s" in str(data.get("duration_unit", "")):
                            entry.latency_ms = round(lat_val * 1000.0, 2)
                        elif lat_val > 10000:
                            entry.latency_ms = round(lat_val / 1000.0, 2)
                        else:
                            entry.latency_ms = round(lat_val, 2)
                    except (ValueError, TypeError):
                        pass

                cls._evaluate_http_status(entry)

            # Détection niveau d'erreur / sévérité JSON
            level = str(data.get("level") or data.get("severity") or data.get("log_level") or "").lower()
            message = str(data.get("message") or data.get("msg") or data.get("error") or data.get("stack") or "")

            if level in ("error", "critical", "fatal", "panic", "emergency") or any(
                p.search(message) for p in cls.CRITICAL_PATTERNS
            ):
                entry.is_error = True
                if level in ("critical", "fatal", "panic", "emergency") or any(p.search(message) for p in cls.CRITICAL_PATTERNS):
                    entry.is_critical_exception = True
                if not entry.error_message:
                    entry.error_message = message[:300] if message else f"JSON log error (level: {level})"

            return True
        except Exception:
            return False

    @staticmethod
    def _evaluate_http_status(entry: ParsedLogEntry):
        """Évalue si un statut HTTP constitue une anomalie ou un échec."""
        if entry.status_code is None:
            return

        if entry.status_code >= 500:
            entry.is_error = True
            entry.error_message = f"HTTP {entry.status_code} sur {entry.http_method or ''} {entry.http_path or ''}".strip()
        elif entry.status_code == 429:
            entry.is_error = True
            entry.error_message = f"Rate Limit (429) sur {entry.http_method or ''} {entry.http_path or ''}".strip()
