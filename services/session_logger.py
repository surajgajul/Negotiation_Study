"""
Session data logger - saves negotiation data to JSON files
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class SessionLogger:
    """Logs session data to JSON files"""

    DATA_DIR = Path(__file__).parent.parent / "data"

    def __init__(self, session_code: str):
        """Initialize logger for a session"""
        self.session_code = session_code
        self.data_dir = self.DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.data_dir / f"{session_code}.json"
        self.session_data = self._load_or_create()

    def _load_or_create(self) -> Dict[str, Any]:
        """Load existing session data or create new"""
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        return {
            "session_code": self.session_code,
            "created_at": datetime.now().isoformat(),
            "rounds": {}
        }

    def _save(self):
        """Save session data to JSON file"""
        with open(self.session_file, 'w') as f:
            json.dump(self.session_data, f, indent=2)

    def log_round_start(self, round_num: int, player_id: int, role: str,
                       reflection_on: bool, initiator: str):
        """Log start of a round"""
        round_key = str(round_num)
        if round_key not in self.session_data["rounds"]:
            self.session_data["rounds"][round_key] = {
                "started_at": datetime.now().isoformat(),
                "player_id": player_id,
                "role": role,
                "reflection_on": reflection_on,
                "initiator": initiator,
                "messages": [],
                "completed": False
            }
        self._save()

    def log_message(self, round_num: int, sender: str, text: str,
                    offer: Optional[int] = None):
        """Log a message in negotiation"""
        round_key = str(round_num)
        if round_key not in self.session_data["rounds"]:
            return

        message = {
            "timestamp": datetime.now().isoformat(),
            "sender": sender,
            "text": text
        }
        if offer is not None:
            message["offer"] = offer

        self.session_data["rounds"][round_key]["messages"].append(message)
        self._save()

    def log_round_complete(self, round_num: int, agreement_reached: bool,
                          final_price: Optional[int] = None):
        """Log completion of a round"""
        round_key = str(round_num)
        if round_key not in self.session_data["rounds"]:
            return

        self.session_data["rounds"][round_key].update({
            "completed": True,
            "completed_at": datetime.now().isoformat(),
            "agreement_reached": agreement_reached,
            "final_price": final_price
        })
        self._save()

    def log_metadata(self, metadata: Dict[str, Any]):
        """Log session metadata"""
        self.session_data.update(metadata)
        self._save()

    def get_session_data(self) -> Dict[str, Any]:
        """Get current session data"""
        return self.session_data

    @staticmethod
    def list_sessions() -> List[str]:
        """List all session files in data directory"""
        data_dir = Path(__file__).parent.parent / "data"
        if not data_dir.exists():
            return []
        return [f.stem for f in data_dir.glob("*.json")]
