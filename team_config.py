"""Team structure loader — reads team_structure.json and provides lookup helpers."""
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_STRUCTURE_FILE = os.path.join(os.path.dirname(__file__), "team_structure.json")

# Team IDs that are actual frontdesk teams (not broadcast/management/kefu)
TEAM_IDS = ["quanxian", "ajun", "hejun", "chaoqun"]


class TeamConfig:
    """Loads and exposes the team structure from team_structure.json."""

    def __init__(self, structure_file: str = _STRUCTURE_FILE):
        self._data: Dict = {}
        self._load(structure_file)

    def _load(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info(f"Team structure loaded from {path}")
        except FileNotFoundError:
            logger.warning(f"team_structure.json not found at {path}, falling back to env vars")
            self._data = {}
        except Exception as e:
            logger.error(f"Failed to load team_structure.json: {e}")
            self._data = {}

    # ── Team group helpers ────────────────────────────────────────────────

    def get_team_chat_id(self, team_id: str) -> Optional[int]:
        """Return chat_id for a team (e.g. 'quanxian', 'ajun')."""
        team = self._data.get(team_id)
        if team:
            return team.get("chat_id")
        return None

    def get_team_topic_id(self, team_id: str, topic_name: str) -> Optional[int]:
        """Return topic message-thread-id by partial name match.

        '日报' matches '📊 日报 Daily Reports'.
        """
        team = self._data.get(team_id)
        if not team:
            return None
        topics: Dict[str, int] = team.get("topics", {})
        # Exact match first
        if topic_name in topics:
            return topics[topic_name]
        # Partial match (case-insensitive)
        topic_lower = topic_name.lower()
        for key, tid in topics.items():
            if topic_lower in key.lower():
                return tid
        return None

    def get_all_team_ids(self) -> List[str]:
        """Return list of frontdesk team IDs (excludes broadcast/management/kefu)."""
        return [k for k in TEAM_IDS if k in self._data]

    # ── Broadcast channel ─────────────────────────────────────────────────

    def get_broadcast_id(self) -> Optional[int]:
        """Return the broadcast channel chat_id."""
        bc = self._data.get("broadcast")
        if bc:
            return bc.get("chat_id")
        # Fallback to env var
        val = os.getenv("BROADCAST_CHANNEL_ID", "").strip()
        if val.lstrip("-").isdigit():
            return int(val)
        return None

    # ── Management group ──────────────────────────────────────────────────

    def get_management_id(self) -> Optional[int]:
        """Return management group chat_id."""
        mgmt = self._data.get("management")
        if mgmt:
            return mgmt.get("chat_id")
        val = os.getenv("MANAGEMENT_CHAT_ID", "").strip()
        if val.lstrip("-").isdigit():
            return int(val)
        return None

    def get_management_topic_id(self, topic_name: str) -> Optional[int]:
        """Return topic id in management group by partial name match."""
        mgmt = self._data.get("management")
        if not mgmt:
            return None
        topics: Dict[str, int] = mgmt.get("topics", {})
        if topic_name in topics:
            return topics[topic_name]
        topic_lower = topic_name.lower()
        for key, tid in topics.items():
            if topic_lower in key.lower():
                return tid
        return None

    # ── Customer service group ────────────────────────────────────────────

    def get_kefu_id(self) -> Optional[int]:
        """Return kefu (customer service) group chat_id."""
        kefu = self._data.get("kefu")
        if kefu:
            return kefu.get("chat_id")
        val = os.getenv("KEFU_CHAT_ID", "").strip()
        if val.lstrip("-").isdigit():
            return int(val)
        return None

    # ── Member → team lookup ──────────────────────────────────────────────

    def get_team_for_member(self, display_name: str) -> Optional[str]:
        """Return team_id for a member by display_name.

        Checks 'members', 'support', and 'leader' fields.
        Returns first match; None if not found.
        """
        name_lower = display_name.lower().strip()
        for team_id in self.get_all_team_ids():
            team = self._data.get(team_id, {})
            members = team.get("members", [])
            support = team.get("support", [])
            leader = team.get("leader", "")
            all_names = members + support + ([leader] if leader else [])
            for n in all_names:
                if n.lower().strip() == name_lower:
                    return team_id
        return None

    # ── Raw access ────────────────────────────────────────────────────────

    def get_team_info(self, team_id: str) -> Optional[Dict]:
        """Return full team dict."""
        return self._data.get(team_id)

    def is_loaded(self) -> bool:
        return bool(self._data)


# Singleton
team_config = TeamConfig()
