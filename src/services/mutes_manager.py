"""Dynamic Mutes & Noise Filter Manager for DokploySentinel."""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MUTES_FILE_PATH = os.getenv("SENTINEL_MUTES_FILE", ".sentinel_mutes.json")


class MuteRule:
    def __init__(
        self,
        pattern: str,
        expires_at: Optional[datetime] = None,
        reason: str = "",
        server_name: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.pattern = pattern.strip().lower()
        self.expires_at = expires_at
        self.reason = reason
        self.server_name = server_name.strip() if server_name else None
        self.created_at = created_at or datetime.now(timezone.utc)

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def remaining_minutes(self) -> Optional[int]:
        if not self.expires_at:
            return None
        now = datetime.now(timezone.utc)
        if now >= self.expires_at:
            return 0
        return int((self.expires_at - now).total_seconds() // 60)

    def matches(self, container_name: str, server_name: Optional[str] = None) -> bool:
        """Vérifie si le conteneur correspond au motif de sourdine."""
        if self.is_expired:
            return False

        if self.server_name and server_name:
            if self.server_name.lower() != server_name.lower():
                return False

        c_name = (container_name or "").lower()
        if self.pattern in ("*", "all"):
            return True
        return self.pattern in c_name

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "remaining_minutes": self.remaining_minutes,
            "reason": self.reason,
            "server_name": self.server_name,
            "created_at": self.created_at.isoformat(),
            "is_permanent": self.expires_at is None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MuteRule":
        expires_at = None
        if data.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(data["expires_at"])
            except Exception:
                pass

        created_at = None
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except Exception:
                pass

        return cls(
            pattern=data.get("pattern", ""),
            expires_at=expires_at,
            reason=data.get("reason", ""),
            server_name=data.get("server_name"),
            created_at=created_at,
        )


class MutesManager:
    def __init__(self, persistence_file: str = MUTES_FILE_PATH):
        self.persistence_file = persistence_file
        self._rules: Dict[str, MuteRule] = {}
        self.load_from_disk()

    def mute(
        self,
        pattern: str,
        duration_minutes: Optional[int] = None,
        reason: str = "Manuel",
        server_name: Optional[str] = None,
    ) -> MuteRule:
        """Ajoute ou met à jour une règle de mise en sourdine."""
        pattern_norm = pattern.strip().lower()
        expires_at = None
        if duration_minutes and duration_minutes > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        rule = MuteRule(
            pattern=pattern_norm,
            expires_at=expires_at,
            reason=reason,
            server_name=server_name,
        )
        self._rules[pattern_norm] = rule
        self.save_to_disk()
        logger.info(
            f"[MutesManager] Règle de sourdine activée pour '{pattern_norm}' (Durée: {duration_minutes or 'Permanente'} min)"
        )
        return rule

    def unmute(self, pattern: str) -> bool:
        """Supprime une règle de mise en sourdine."""
        pattern_norm = pattern.strip().lower()
        if pattern_norm in self._rules:
            del self._rules[pattern_norm]
            self.save_to_disk()
            logger.info(f"[MutesManager] Sourdine levée pour '{pattern_norm}'.")
            return True
        return False

    def is_muted(self, container_name: str, server_name: Optional[str] = None) -> bool:
        """Vérifie si un conteneur est actuellement sous une règle de sourdine active."""
        self._clean_expired()
        for rule in self._rules.values():
            if rule.matches(container_name, server_name):
                return True
        return False

    def get_active_mutes(self) -> List[dict]:
        """Retourne la liste des règles de sourdine actives."""
        self._clean_expired()
        return [rule.to_dict() for rule in self._rules.values()]

    def clear_all(self):
        """Réinitialise toutes les règles de sourdine."""
        self._rules.clear()
        self.save_to_disk()

    def _clean_expired(self):
        """Nettoie les règles expirées."""
        expired = [k for k, rule in self._rules.items() if rule.is_expired]
        if expired:
            for k in expired:
                del self._rules[k]
            self.save_to_disk()

    def save_to_disk(self):
        """Sauvegarde les règles sur le disque pour survivre aux redémarrages."""
        try:
            data = [rule.to_dict() for rule in self._rules.values() if not rule.is_expired]
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"[MutesManager] Impossible de persister les mutes sur disque : {e}")

    def load_from_disk(self):
        """Charge les règles persistées depuis le disque."""
        if not os.path.exists(self.persistence_file):
            return
        try:
            with open(self.persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    rule = MuteRule.from_dict(item)
                    if not rule.is_expired:
                        self._rules[rule.pattern] = rule
            logger.info(f"[MutesManager] {len(self._rules)} règles de sourdine chargées depuis le disque.")
        except Exception as e:
            logger.debug(f"[MutesManager] Impossible de lire les mutes depuis le disque : {e}")


mutes_manager = MutesManager()
