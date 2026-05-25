# backend/app/utils/session_manager.py

"""
EMMA Session Manager
====================
Manages the saving and loading of agent session states to 'sessions.json'.
Integrates with PageCurveEvaporator to automatically compress log entries before saving.
"""

import os
import json
import logging
from typing import Any, Dict, Optional
from app.core.context_scheduler import PageCurveEvaporator

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages session serialization and deserialization.
    Ensures that saved session states are compressed to prevent database bloat.
    """
    def __init__(self, db_path: str = "sessions.json", max_log_lines: int = 15):
        self.db_path = db_path
        self.evaporator = PageCurveEvaporator(max_lines=max_log_lines)
        logger.info("SessionManager initialized with db_path=%s, max_log_lines=%d", db_path, max_log_lines)

    def _load_db(self) -> Dict[str, Any]:
        """Loads the raw session database."""
        if not os.path.exists(self.db_path):
            return {}
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load session database: %s. Creating new one.", e)
            return {}

    def _save_db(self, data: Dict[str, Any]) -> None:
        """Saves the session database atomically to disk."""
        tmp_path = f"{self.db_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            os.replace(tmp_path, self.db_path)
        except Exception as e:
            logger.error("Failed to save session database: %s", e)
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a session state by ID."""
        db = self._load_db()
        return db.get(session_id)

    def save_session(self, session_id: str, session_state: Dict[str, Any]) -> None:
        """
        Compresses and saves a session state.
        Evaporates any long console logs inside the session state to keep the file small.
        """
        # Compress active log entries using the PageCurveEvaporator
        if "logs" in session_state and isinstance(session_state["logs"], list):
            compressed_logs = []
            for entry in session_state["logs"]:
                if isinstance(entry, dict) and "output" in entry and isinstance(entry["output"], str):
                    raw_output = entry["output"]
                    # Evaporate the log if it exceeds the max lines
                    evaporated = self.evaporator.evaporate_log(raw_output)
                    entry["output"] = evaporated
                compressed_logs.append(entry)
            session_state["logs"] = compressed_logs

        db = self._load_db()
        db[session_id] = session_state
        self._save_db(db)
        logger.info("Session %s successfully compressed and saved.", session_id)
