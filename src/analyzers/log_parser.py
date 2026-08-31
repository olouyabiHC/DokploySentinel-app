"""Log parser for extracting HTTP status, latencies, and critical exceptions from container logs."""

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
    # Pattern standard pour logs d'accès Nginx / Gunicorn / Traefik
    # Ex: '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "POST /path/ HTTP/1.1" 200 122 "ref" "ua" 80202'
    HTTP_ACCESS_REGEX = re.compile(
        r'"(?P<method>[A-Z]+)\s+(?P<path>[^\s]+)\s+HTTP/[0-9.]+"\s+(?P<status>\d{3})\s+\d+.*?(?P<latency>\d+)?$'
    )

    # Patterns critiques (crashes, tracebacks, fatal errors)
    CRITICAL_PATTERNS = [
        re.compile(r'Traceback \(most recent call last\):', re.IGNORECASE),
        re.compile(r'Internal Server Error', re.IGNORECASE),
        re.compile(r'Fatal error:', re.IGNORECASE),
        re.compile(r'Uncaught Exception:', re.IGNORECASE),
        re.compile(r'panic:', re.IGNORECASE),
        re.compile(r'OOMKilled', re.IGNORECASE),
        re.compile(r'DatabaseError|OperationalError|ConnectionRefusedError', re.IGNORECASE),
        re.compile(r'\[CRITICAL\]|\[FATAL\]|\[ERROR\]', re.IGNORECASE),
    ]

    @classmethod
    def parse_line(cls, line: str, container_name: str) -> ParsedLogEntry:
        line_clean = line.strip()
        entry = ParsedLogEntry(raw_line=line_clean, container_name=container_name)

        # 1. Vérifier si c'est un log d'accès HTTP
        match = cls.HTTP_ACCESS_REGEX.search(line_clean)
        if match:
            entry.is_http_request = True
            entry.http_method = match.group("method")
            entry.http_path = match.group("path")
            entry.status_code = int(match.group("status"))
            
            # Latence (si présente en microsecondes ou millisecondes)
            latency_raw = match.group("latency")
            if latency_raw:
                val = float(latency_raw)
                # Si valeur > 10000, c'est probablement des microsecondes
                entry.latency_ms = val / 1000.0 if val > 10000 else val

            if entry.status_code >= 500:
                entry.is_error = True
                entry.error_message = f"HTTP {entry.status_code} on {entry.http_method} {entry.http_path}"
            elif entry.status_code == 429:
                entry.is_error = True
                entry.error_message = f"Rate Limited (429) on {entry.http_method} {entry.http_path}"
            
            return entry

        # 2. Vérifier si c'est une exception ou erreur critique
        for pattern in cls.CRITICAL_PATTERNS:
            if pattern.search(line_clean):
                entry.is_critical_exception = True
                entry.is_error = True
                entry.error_message = line_clean[:300]
                break

        return entry
